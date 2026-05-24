"""Universe build orchestration — collect, filter, persist."""

from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Optional

from src.trading.competition.constants import (
    MAX_ENTRY_PRICE_KRW,
    MIN_AVG_TRADING_VALUE_KRW,
)
from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.base import ROOT, save_json_file
from src.trading.competition.universe.collector import collect_all_stocks
from src.trading.competition.universe.filters import assess_kis_risk
from src.trading.competition.universe.models import SymbolSnapshot
from src.trading.competition.universe.security_type import classify_security_type

logger = logging.getLogger(__name__)

UNIVERSE_DIR = ROOT / "data" / "competition" / "universe"
ALL_STOCKS_PATH = UNIVERSE_DIR / "all_stocks.json"
ELIGIBLE_PATH = UNIVERSE_DIR / "eligible_entry_universe.json"
EXCLUDED_PATH = UNIVERSE_DIR / "excluded_stocks.json"
SUMMARY_PATH = UNIVERSE_DIR / "build_summary.json"


def _kis_quote_fetcher(ticker: str) -> dict[str, Any] | None:
    try:
        from data.kis_client import get_price

        return get_price(ticker.zfill(6))
    except Exception:
        return None


def enrich_risk_from_kis(
    records: list[dict[str, Any]],
    *,
    max_workers: int = 8,
    kis_fetcher: Callable[[str], dict[str, Any] | None] | None = None,
) -> tuple[int, int]:
    """Fetch KIS risk for records in-place. Returns (verified_count, failed_count)."""
    try:
        from data.kis_client import is_kis_auth_failed

        if is_kis_auth_failed():
            for rec in records:
                rec["risk_check_status"] = "unverified"
                rec["risk_status"] = "unknown"
                rec["risk_exclude_new_entry"] = False
                rec["risk_notes"] = ["kis_auth_failed"]
            return 0, len(records)
        from data.kis_client import is_kis_rate_limit_halted

        if is_kis_rate_limit_halted():
            for rec in records:
                rec["risk_check_status"] = "unverified"
                rec["risk_status"] = "unknown"
                rec["risk_exclude_new_entry"] = False
                rec["risk_notes"] = ["kis_rate_limit_exceeded"]
            return 0, len(records)
    except Exception:
        pass

    fetcher = kis_fetcher or _kis_quote_fetcher
    verified = 0
    failed = 0

    def _one(rec: dict[str, Any]) -> bool:
        quote = fetcher(rec["ticker"])
        if not quote:
            rec["risk_check_status"] = "unverified"
            rec["risk_status"] = "unknown"
            rec["risk_exclude_new_entry"] = False
            rec["risk_notes"] = []
            return False
        raw = quote.get("raw") or {}
        risk = assess_kis_risk(raw if isinstance(raw, dict) else None)
        rec["risk_check_status"] = "verified"
        rec["risk_status"] = risk["risk_status"]
        rec["risk_exclude_new_entry"] = bool(risk["exclude_new_entry"])
        rec["risk_notes"] = list(risk.get("notes") or [])
        rec["tradable"] = risk.get("tradable")
        if "kis" not in rec.get("data_sources", []):
            rec.setdefault("data_sources", []).append("kis")
        return True

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_one, rec) for rec in records]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    verified += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                logger.warning("KIS risk fetch error: %s", exc)

    return verified, failed


def record_to_snapshot(rec: dict[str, Any]) -> SymbolSnapshot:
    sec_type = classify_security_type(rec.get("name", ""), rec.get("ticker", ""))
    risk_verified = rec.get("risk_check_status") == "verified"
    return SymbolSnapshot(
        ticker=str(rec["ticker"]).zfill(6),
        name=str(rec.get("name") or rec["ticker"]),
        market=rec.get("market", "UNKNOWN"),  # type: ignore[arg-type]
        security_type=sec_type,  # type: ignore[arg-type]
        current_price_krw=rec.get("current_price_krw"),
        avg_trading_value_20d_krw=rec.get("avg_trading_value_20d_krw"),
        risk_status=rec.get("risk_status", "normal") if risk_verified else "normal",  # type: ignore[arg-type]
        risk_exclude_new_entry=bool(rec.get("risk_exclude_new_entry")) if risk_verified else False,
        risk_notes=list(rec.get("risk_notes") or []),
        tradable=rec.get("tradable") if rec.get("tradable") is not None else True,
    )


def evaluate_entry_eligibility(rec: dict[str, Any]) -> tuple[bool, str, str]:
    """
    Evaluate new-entry eligibility with mandatory field checks.

    Returns (eligible, reason_code, reason_category).
    reason_category groups for build_summary counts.
    """
    sec_type = classify_security_type(rec.get("name", ""), rec.get("ticker", ""))
    rec["security_type"] = sec_type

    if not rec.get("name"):
        return False, "data_unavailable:missing_name", "data_unavailable"

    if sec_type == "unknown":
        return False, "data_unavailable:unknown_security_type", "data_unavailable"

    if sec_type != "common":
        return False, f"excluded_security_type:{sec_type}", "excluded_security_type"

    price = rec.get("current_price_krw")
    if price is None:
        return False, "data_unavailable:no_price", "data_unavailable"

    avg_tv = rec.get("avg_trading_value_20d_krw")
    if avg_tv is None:
        hist = rec.get("history_days_present", 0)
        if hist < 15:
            return False, "data_unavailable:insufficient_history", "data_unavailable"
        return False, "data_unavailable:no_avg_trading_value_20d", "data_unavailable"

    if rec.get("risk_check_status") != "verified":
        return False, "data_unavailable:risk_unverified", "data_unavailable"

    risk_status = rec.get("risk_status")
    if risk_status in (None, "unknown"):
        return False, "data_unavailable:risk_unverified", "data_unavailable"

    if rec.get("risk_exclude_new_entry"):
        return False, f"risk:{risk_status}", "risk"

    if price > MAX_ENTRY_PRICE_KRW:
        return False, f"price_over_{MAX_ENTRY_PRICE_KRW}", "price_over_limit"

    if avg_tv < MIN_AVG_TRADING_VALUE_KRW:
        return False, f"avg_tv_below_{MIN_AVG_TRADING_VALUE_KRW}", "low_liquidity"

    if rec.get("tradable") is False:
        return False, "not_tradable", "not_tradable"

    return True, "ok", "eligible"


def build_universe(
    trading_date: str,
    *,
    enable_kis_risk: bool = True,
    kis_workers: int = 8,
    pykrx_collector: Callable[..., tuple[list[dict[str, Any]], list[str]]] | None = None,
    kis_fetcher: Callable[[str], dict[str, Any] | None] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Full universe build pipeline."""
    out_dir = output_dir or UNIVERSE_DIR
    collector = pykrx_collector or collect_all_stocks

    all_stocks, collect_errors = collector(trading_date)
    for rec in all_stocks:
        rec.setdefault("security_type", classify_security_type(rec.get("name", ""), rec["ticker"]))
        rec.setdefault("risk_check_status", "pending")
        rec.setdefault("data_sources", ["pykrx"])

    kis_verified = 0
    kis_failed = 0
    if enable_kis_risk and all_stocks:
        kis_verified, kis_failed = enrich_risk_from_kis(
            all_stocks, max_workers=kis_workers, kis_fetcher=kis_fetcher
        )
    else:
        for rec in all_stocks:
            rec["risk_check_status"] = "skipped"
            rec["risk_status"] = "unknown"

    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    filter_counts: Counter[str] = Counter()
    market_counts = Counter(rec.get("market", "UNKNOWN") for rec in all_stocks)

    for rec in all_stocks:
        ok, reason, category = evaluate_entry_eligibility(rec)
        rec["filter_reason"] = reason
        rec["filter_category"] = category
        if ok:
            eligible.append(rec)
            filter_counts["eligible"] += 1
        else:
            excluded.append(rec)
            filter_counts[category] += 1
            filter_counts[reason] += 1

    has_data_gaps = bool(collect_errors) or kis_failed > 0 or any(
        r.get("filter_category") == "data_unavailable" for r in excluded
    )

    summary = {
        "generated_at": now_kst_iso(),
        "trading_date": trading_date,
        "total_collected": len(all_stocks),
        "kospi_count": market_counts.get("KOSPI", 0),
        "kosdaq_count": market_counts.get("KOSDAQ", 0),
        "eligible_count": len(eligible),
        "excluded_count": len(excluded),
        "filter_exclusion_counts": dict(sorted(filter_counts.items())),
        "data_sources": {
            "pykrx": True,
            "kis_risk": enable_kis_risk,
            "kis_risk_verified": kis_verified,
            "kis_risk_failed": kis_failed,
        },
        "collection_errors": collect_errors,
        "has_missing_or_failed_data": has_data_gaps,
    }

    payload_base = {
        "generated_at": summary["generated_at"],
        "trading_date": trading_date,
    }

    save_json_file(out_dir / "all_stocks.json", {**payload_base, "stocks": all_stocks})
    save_json_file(
        out_dir / "eligible_entry_universe.json",
        {**payload_base, "count": len(eligible), "stocks": eligible},
    )
    save_json_file(
        out_dir / "excluded_stocks.json",
        {**payload_base, "count": len(excluded), "stocks": excluded},
    )
    save_json_file(out_dir / "build_summary.json", summary)

    return {
        "ok": len(all_stocks) > 0,
        "summary": summary,
        "paths": {
            "all_stocks": str(out_dir / "all_stocks.json"),
            "eligible": str(out_dir / "eligible_entry_universe.json"),
            "excluded": str(out_dir / "excluded_stocks.json"),
            "summary": str(out_dir / "build_summary.json"),
        },
    }


def load_eligible_universe(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or ELIGIBLE_PATH
    if not p.is_file():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return list(data.get("stocks") or [])
