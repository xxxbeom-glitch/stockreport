"""Build eligible universe for REPLAY (KIS/static primary, pykrx only with KRX credentials)."""

from __future__ import annotations

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.trading.competition.constants import MAX_ENTRY_PRICE_KRW, MIN_AVG_TRADING_VALUE_KRW
from src.trading.competition.universe.builder import (
    ALL_STOCKS_PATH,
    enrich_risk_from_kis,
    evaluate_entry_eligibility,
)
from src.trading.competition.universe.collector import collect_all_stocks
from src.trading.competition.universe.security_type import classify_security_type

logger = logging.getLogger(__name__)

STATIC_MASTER_PATH = ALL_STOCKS_PATH.parent / "static_ticker_master.json"
KIS_VOLUME_RANK_PER_MARKET = 180


@dataclass
class UniverseStageCounts:
    trading_date: str
    base_universe_source: str = ""
    base_universe_count: int = 0
    security_prefilter_excluded_count: int = 0
    common_stock_candidate_count: int = 0
    kis_enrich_target_count: int = 0
    historical_price_enriched_count: int = 0
    price_filter_pass_count: int = 0
    liquidity_filter_pass_count: int = 0
    risk_filter_pass_count: int = 0
    final_eligible_universe_count: int = 0
    filter_exclusion_counts: dict[str, int] = field(default_factory=dict)
    collection_errors: list[str] = field(default_factory=list)
    kis_risk_verified: int = 0
    kis_risk_failed: int = 0
    day_progress_stopped: bool = False
    day_progress_reason: str | None = None
    ohlcv_cursor_index: int = 0
    risk_cursor_index: int = 0
    next_ticker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def load_static_ticker_master() -> list[dict[str, Any]]:
    """Ticker/name/market master (no as-of prices)."""
    for path in (STATIC_MASTER_PATH, ALL_STOCKS_PATH):
        if not path.is_file():
            continue
        data = _read_json(path)
        rows: list[dict[str, Any]] = []
        for row in data.get("stocks") or []:
            ticker = str(row.get("ticker", "")).zfill(6)
            if not ticker:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "name": str(row.get("name") or ticker),
                    "market": row.get("market", "UNKNOWN"),
                    "avg_trading_value_20d_krw": row.get("avg_trading_value_20d_krw"),
                    "data_sources": ["static_master"],
                }
            )
        if rows:
            return rows
    return []


def collect_base_universe_kis_volume(
    trading_date: str,
    *,
    per_market: int = KIS_VOLUME_RANK_PER_MARKET,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Seed universe from KIS volume-rank (no pykrx ticker list)."""
    from data.kis_client import credentials_ready, get_daily_ohlcv_range, get_top_volume

    errors: list[str] = []
    if not credentials_ready():
        return [], ["kis_credentials_missing"]

    from data.kis_client import is_kis_auth_failed

    if is_kis_auth_failed():
        return [], ["kis_auth_failed"]

    from data.kis_client import is_kis_rate_limit_halted

    if is_kis_rate_limit_halted():
        return [], ["kis_rate_limit_exceeded"]

    start = (datetime.strptime(trading_date, "%Y%m%d") - timedelta(days=45)).strftime("%Y%m%d")
    records: dict[str, dict[str, Any]] = {}

    for market in ("KOSPI", "KOSDAQ"):
        leaders = get_top_volume(market, n=per_market) or []
        if not leaders:
            errors.append(f"kis_volume_rank_empty:{market}")
            continue
        for row in leaders:
            ticker = str(row.get("ticker", "")).zfill(6)
            if not ticker:
                continue
            records[ticker] = {
                "ticker": ticker,
                "name": str(row.get("name") or ticker),
                "market": market,
                "current_price_krw": int(row.get("price") or 0) or None,
                "data_sources": ["kis_volume_rank"],
            }

    out: list[dict[str, Any]] = []
    for rec in records.values():
        ticker = rec["ticker"]
        try:
            bars = get_daily_ohlcv_range(ticker, start, trading_date)
        except Exception as exc:
            errors.append(f"kis_ohlcv:{ticker}:{type(exc).__name__}")
            continue
        if not bars:
            errors.append(f"kis_ohlcv_empty:{ticker}")
            continue
        day = next((b for b in reversed(bars) if str(b.get("date")) == trading_date), bars[-1])
        tv_vals = [int(b.get("trading_value") or 0) for b in bars if int(b.get("trading_value") or 0) > 0]
        if tv_vals:
            rec["avg_trading_value_20d_krw"] = int(sum(tv_vals) / len(tv_vals))
            rec["history_days_present"] = len(tv_vals)
        close = int(day.get("close") or 0)
        if close > 0:
            rec["current_price_krw"] = close
        out.append(rec)

    return out, errors


def _enrich_one_record(rec: dict[str, Any], trading_date: str, start: str) -> tuple[dict[str, Any], bool]:
    from src.trading.competition.replay.data_provider import _load_ticker_ohlcv_map, ohlcv_for_ticker_date

    ticker = str(rec["ticker"]).zfill(6)
    day, source, _ = ohlcv_for_ticker_date(ticker, trading_date)
    if not day or int(day.get("close") or 0) <= 0:
        return rec, False
    rec["current_price_krw"] = int(day["close"])
    rec["current_trading_value_krw"] = int(day.get("tv") or 0)
    bars_map, _, _ = _load_ticker_ohlcv_map(ticker, start, trading_date)
    tv_vals = [int(v.get("tv") or 0) for v in bars_map.values() if int(v.get("tv") or 0) > 0]
    if tv_vals:
        rec["avg_trading_value_20d_krw"] = int(sum(tv_vals) / len(tv_vals))
        rec["history_days_present"] = len(tv_vals)
    sources = list(rec.get("data_sources") or [])
    tag = "kis_historical" if source and str(source).startswith("kis") else "replay_ohlcv"
    if tag not in sources:
        sources.append(tag)
    rec["data_sources"] = sources
    return rec, True


def common_stock_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """KOSPI/KOSDAQ 일반 보통주만 (ETF/우선주/SPAC/리츠 등 제외) — KIS 호출 전 분류."""
    return [
        r
        for r in records
        if classify_security_type(str(r.get("name") or ""), str(r.get("ticker") or "")) == "common"
    ]


def enrich_records_for_trading_date(
    records: list[dict[str, Any]],
    trading_date: str,
    *,
    start_index: int = 0,
) -> tuple[int, list[str], int, bool, int]:
    """
    KIS OHLCV enrich for common stocks (sequential cursor; no repeat on resume).
    Returns (enriched_count, errors, target_count, stopped_early, next_index).
    """
    from src.trading.competition.replay.data_provider import _kis_ready
    from src.trading.competition.replay.day_progress import is_record_ohlcv_enriched

    if not _kis_ready():
        return 0, ["kis_credentials_missing"], 0, False, 0

    from data.kis_client import is_kis_auth_failed

    if is_kis_auth_failed():
        return 0, ["kis_auth_failed"], 0, False, 0

    from data.kis_client import is_kis_rate_limit_halted
    from data.kis_rate_limit import is_kis_request_budget_reached

    if is_kis_rate_limit_halted():
        return 0, ["kis_rate_limit_exceeded"], 0, True, start_index

    start = (datetime.strptime(trading_date, "%Y%m%d") - timedelta(days=45)).strftime("%Y%m%d")
    candidates = common_stock_records(records)
    candidates.sort(key=lambda r: str(r.get("ticker") or "").zfill(6))
    target_n = len(candidates)

    enriched = 0
    errors: list[str] = []
    next_index = start_index

    for i, rec in enumerate(candidates):
        if i < start_index:
            if is_record_ohlcv_enriched(rec, trading_date):
                enriched += 1
            continue
        if is_record_ohlcv_enriched(rec, trading_date):
            enriched += 1
            next_index = i + 1
            continue
        if is_kis_rate_limit_halted():
            return enriched, errors + ["kis_rate_limit_exceeded"], target_n, True, i
        if is_kis_request_budget_reached():
            return enriched, errors + ["kis_request_budget_reached"], target_n, True, i
        row = dict(rec)
        _, ok = _enrich_one_record(row, trading_date, start)
        rec.clear()
        rec.update(row)
        if ok:
            rec["_ohlcv_enriched_date"] = trading_date
            enriched += 1
        next_index = i + 1

    return enriched, errors, target_n, False, next_index


def _count_filter_stages(records: list[dict[str, Any]]) -> tuple[int, int, int]:
    price_pass = liquidity_pass = risk_pass = 0
    for rec in records:
        price = rec.get("current_price_krw")
        if price is None or int(price) <= 0 or int(price) > MAX_ENTRY_PRICE_KRW:
            continue
        price_pass += 1
        avg_tv = rec.get("avg_trading_value_20d_krw")
        if avg_tv is None or int(avg_tv) < MIN_AVG_TRADING_VALUE_KRW:
            continue
        liquidity_pass += 1
        if rec.get("risk_check_status") != "verified":
            continue
        if rec.get("risk_exclude_new_entry"):
            continue
        if rec.get("risk_status") in (None, "unknown"):
            continue
        risk_pass += 1
    return price_pass, liquidity_pass, risk_pass


def build_eligible_universe_for_replay(
    trading_date: str,
    *,
    campaign_id: str | None = None,
) -> tuple[list[dict[str, Any]], UniverseStageCounts]:
    """
    Build as-of trading_date eligible universe for REPLAY snapshot.
    Never calls pykrx without KRX_ID/KRX_PW.
    """
    from src.trading.competition.replay.data_provider import _kis_ready
    from src.trading.competition.replay.pykrx_safe import krx_credentials_configured

    from src.trading.competition.replay.day_progress import (
        PHASE_OHLCV,
        PHASE_RISK,
        clear_day_progress,
        load_day_progress,
        load_partial_day_records,
        merge_master_with_partial,
        save_day_progress,
    )

    counts = UniverseStageCounts(trading_date=trading_date)
    base: list[dict[str, Any]] = []
    progress = load_day_progress(campaign_id) if campaign_id else None
    if progress and str(progress.get("trading_date")) != trading_date:
        clear_day_progress(campaign_id, trading_date=str(progress.get("trading_date") or ""))
        progress = None
    phase = str(progress.get("phase") or PHASE_OHLCV) if progress else PHASE_OHLCV

    if _kis_ready() and not krx_credentials_configured():
        from data.kis_client import preflight_kis_auth

        auth = preflight_kis_auth()
        if not auth.get("ok"):
            counts.collection_errors.append(str(auth.get("error") or "kis_auth_failed"))
            counts.filter_exclusion_counts = {"kis_auth_failed": 1}
            logger.error("replay_universe kis_auth_failed %s", auth)
            return [], counts

    if krx_credentials_configured():
        base, errs = collect_all_stocks(trading_date)
        counts.base_universe_source = "pykrx"
        counts.collection_errors.extend(errs)
    else:
        master = load_static_ticker_master()
        if master:
            partial = (
                load_partial_day_records(campaign_id, trading_date)
                if campaign_id and progress
                else None
            )
            base = merge_master_with_partial(master, partial)
            counts.base_universe_source = "static_master"
            common_rows = common_stock_records(base)
            counts.common_stock_candidate_count = len(common_rows)
            counts.security_prefilter_excluded_count = len(base) - len(common_rows)
            if phase == PHASE_OHLCV:
                ohlcv_start = int(progress.get("ohlcv_cursor_index") or 0) if progress else 0
                enriched, enrich_errs, target_n, stopped, next_idx = enrich_records_for_trading_date(
                    common_rows,
                    trading_date,
                    start_index=ohlcv_start,
                )
                counts.kis_enrich_target_count = target_n
                counts.historical_price_enriched_count = enriched
                counts.ohlcv_cursor_index = next_idx
                counts.collection_errors.extend(enrich_errs[:20])
                if stopped:
                    reason = enrich_errs[-1] if enrich_errs else "kis_request_budget_reached"
                    counts.day_progress_stopped = True
                    counts.day_progress_reason = reason
                    next_t = (
                        str(common_rows[next_idx].get("ticker")).zfill(6)
                        if next_idx < len(common_rows)
                        else None
                    )
                    counts.next_ticker = next_t
                    if campaign_id:
                        save_day_progress(
                            campaign_id,
                            {
                                "trading_date": trading_date,
                                "phase": PHASE_OHLCV,
                                "ohlcv_cursor_index": next_idx,
                                "risk_cursor_index": 0,
                                "next_ticker": next_t,
                                "resume_reason": reason,
                            },
                            records=base,
                        )
                    return [], counts
                phase = PHASE_RISK
                if campaign_id:
                    save_day_progress(
                        campaign_id,
                        {
                            "trading_date": trading_date,
                            "phase": PHASE_RISK,
                            "ohlcv_cursor_index": next_idx,
                            "risk_cursor_index": 0,
                            "next_ticker": None,
                        },
                        records=base,
                    )
        else:
            base, errs = collect_base_universe_kis_volume(trading_date)
            counts.base_universe_source = "kis_volume_rank"
            counts.collection_errors.extend(errs)
            counts.historical_price_enriched_count = sum(
                1 for r in base if int(r.get("current_price_krw") or 0) > 0
            )

    counts.base_universe_count = len(base)

    if not base:
        logger.warning("replay_universe base empty date=%s source=%s", trading_date, counts.base_universe_source)
        return [], counts

    for rec in base:
        rec.setdefault("risk_check_status", "pending")
        rec.setdefault("data_sources", list(rec.get("data_sources") or []))

    risk_targets = common_stock_records(base) if base else []
    from data.kis_rate_limit import configured_enrich_max_workers

    risk_start = int(progress.get("risk_cursor_index") or 0) if progress and phase == PHASE_RISK else 0
    verified, failed, risk_stopped, risk_next = enrich_risk_from_kis(
        risk_targets,
        max_workers=configured_enrich_max_workers(),
        start_index=risk_start,
        sequential=True,
    )
    counts.kis_risk_verified = verified
    counts.kis_risk_failed = failed
    counts.risk_cursor_index = risk_next
    if risk_stopped:
        reason = "kis_rate_limit_exceeded"
        from data.kis_rate_limit import is_kis_request_budget_reached

        if is_kis_request_budget_reached():
            reason = "kis_request_budget_reached"
        counts.day_progress_stopped = True
        counts.day_progress_reason = reason
        next_t = (
            str(risk_targets[risk_next].get("ticker")).zfill(6)
            if risk_next < len(risk_targets)
            else None
        )
        counts.next_ticker = next_t
        if campaign_id:
            save_day_progress(
                campaign_id,
                {
                    "trading_date": trading_date,
                    "phase": PHASE_RISK,
                    "ohlcv_cursor_index": counts.ohlcv_cursor_index or len(risk_targets),
                    "risk_cursor_index": risk_next,
                    "next_ticker": next_t,
                    "resume_reason": reason,
                },
                records=base,
            )
        return [], counts

    if campaign_id:
        clear_day_progress(campaign_id, trading_date=trading_date)

    eligible: list[dict[str, Any]] = []
    exclusion: Counter[str] = Counter()

    for rec in base:
        ok, reason, category = evaluate_entry_eligibility(rec)
        rec["filter_reason"] = reason
        rec["filter_category"] = category
        exclusion[category] += 1
        exclusion[reason] += 1
        if ok:
            eligible.append(rec)

    counts.price_filter_pass_count, counts.liquidity_filter_pass_count, counts.risk_filter_pass_count = (
        _count_filter_stages(base)
    )
    counts.final_eligible_universe_count = len(eligible)
    counts.filter_exclusion_counts = dict(sorted(exclusion.items()))

    logger.info(
        "replay_universe date=%s source=%s base=%s enriched=%s final=%s price_pass=%s liq_pass=%s risk_pass=%s",
        trading_date,
        counts.base_universe_source,
        counts.base_universe_count,
        counts.historical_price_enriched_count,
        counts.final_eligible_universe_count,
        counts.price_filter_pass_count,
        counts.liquidity_filter_pass_count,
        counts.risk_filter_pass_count,
    )
    return eligible, counts


def log_universe_counts(counts: UniverseStageCounts) -> None:
    """Structured log for observability / GHA step summary."""
    payload = counts.to_dict()
    logger.info("replay_universe_stage_counts %s", payload)
