# -*- coding: utf-8 -*-
"""AI 추천 입력용 후보 분리·컨텍스트 수집 (추천 AI 호출 없음)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.models import MAX_DISPLAY_PRICE, SECTOR_GROUPS, SECTOR_LABELS
from agents.mock_trading.universe_builder import _collect_low_cost_metrics

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "data" / "mock_trading"

MIN_AVG_TV_5D_AI = 3_000_000_000  # 30억

def _first_sentence(text: str, max_len: int = 160) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return ""
    for sep in (". ", "。 ", "\n"):
        if sep in t:
            t = t.split(sep)[0].strip()
            break
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def _avg_tv(row: dict[str, Any]) -> int | None:
    v = (row.get("metrics") or {}).get("avg_trading_value_5d")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def is_ai_input_eligible(row: dict[str, Any]) -> tuple[bool, str]:
    """candidate_universe 후보 1건이 AI 입력 조건 충족 여부."""
    code = str(row.get("ticker") or "").zfill(6)
    market = str(row.get("market") or "").upper()
    m_status = str(row.get("market_check_status") or "")
    if market != "KOSDAQ" and m_status != "verified":
        return False, "not_kosdaq_verified"

    price = row.get("current_price")
    if price is None:
        return False, "no_price"
    try:
        p = int(price)
    except (TypeError, ValueError):
        return False, "invalid_price"
    if p > MAX_DISPLAY_PRICE:
        return False, "price_over_59000"

    filters = row.get("filters") or {}
    if filters.get("tradable") is False:
        return False, "not_tradable"
    if filters.get("price_under_59000") is False:
        return False, "price_filter_false"

    avg = _avg_tv(row)
    if avg is None:
        return False, "no_avg_trading_value_5d"
    if avg < MIN_AVG_TV_5D_AI:
        return False, f"avg_tv_below_{MIN_AVG_TV_5D_AI}"

    return True, "ok"


def filter_ai_input_candidates(
    base_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(ai_input_list, excluded_with_reason)"""
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in base_candidates:
        ok, reason = is_ai_input_eligible(row)
        code = str(row.get("ticker") or "").zfill(6)
        if ok:
            selected.append(row)
        else:
            excluded.append(
                {
                    "ticker": code,
                    "name": row.get("name"),
                    "reason": reason,
                    "avg_trading_value_5d": _avg_tv(row),
                }
            )
    return selected, excluded


def build_ai_input_candidates_doc(
    universe_doc: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    dt = now or datetime.now(KST)
    base = list(universe_doc.get("candidates") or [])
    selected, excluded = filter_ai_input_candidates(base)

    sector_counts: dict[str, int] = {sk: 0 for sk in SECTOR_GROUPS}
    for row in selected:
        for sk in row.get("sector_keys") or [row.get("sector_group")]:
            if sk in sector_counts:
                sector_counts[sk] += 1

    return {
        "generated_at": dt.isoformat(timespec="seconds"),
        "selection_rule": {
            "market": "KOSDAQ",
            "market_check": "verified",
            "max_price": MAX_DISPLAY_PRICE,
            "min_avg_trading_value_5d": MIN_AVG_TV_5D_AI,
            "risk_exclusion_applied": True,
            "source_file": "candidate_universe.json",
        },
        "summary": {
            "base_candidate_count": len(base),
            "ai_input_candidate_count": len(selected),
            "excluded_from_base_count": len(excluded),
            "sector_counts": sector_counts,
            "sector_labels": {sk: SECTOR_LABELS.get(sk, sk) for sk in SECTOR_GROUPS},
        },
        "candidates": selected,
        "excluded_from_ai_input": excluded,
    }


def _normalize_news_items(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in raw[:3]:
        if not isinstance(row, dict):
            continue
        desc = str(row.get("description") or "").strip()
        out.append(
            {
                "title": str(row.get("title") or "").strip(),
                "published_at": str(row.get("pubDate") or row.get("published_at") or ""),
                "source": str(row.get("source") or "naver_search_news"),
                "summary": _first_sentence(desc, 200) if desc else "",
            }
        )
    return out


def _normalize_disclosures(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in raw[:3]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "title": str(row.get("report_nm") or row.get("title") or "").strip(),
                "published_at": str(row.get("rcept_dt") or row.get("published_at") or ""),
                "importance": "important",
            }
        )
    return out


def build_stock_context(
    row: dict[str, Any],
    *,
    collect_news: bool = True,
    collect_disclosure: bool = True,
    refresh_metrics: bool = True,
) -> tuple[dict[str, Any], dict[str, str]]:
    """
    종목 1건 컨텍스트 + 수집 상태 플래그(news/disclosure/flow: ok|fail|empty|skip).
    """
    code = str(row.get("ticker") or "").zfill(6)
    name = str(row.get("name") or code)
    sector_keys = list(row.get("sector_keys") or [])
    primary_key = (
        (sector_keys[0] if sector_keys else None)
        or row.get("sector_group")
        or ""
    )
    sector_for_news = SECTOR_LABELS.get(str(primary_key), str(primary_key))

    filters = row.get("filters") or {}
    warnings = {
        "investment_caution": filters.get("warning_flag") == "investment_caution",
        "risk_notes": list(filters.get("risk_notes") or []),
    }

    metrics: dict[str, Any] = dict(row.get("metrics") or {})
    collect_errors: list[str] = []
    status: dict[str, str] = {
        "price": "ok" if row.get("current_price") is not None else "fail",
        "flow": "skip",
        "news": "skip",
        "disclosure": "skip",
    }

    if refresh_metrics:
        try:
            refreshed, _ = _collect_low_cost_metrics(
                code, name, sector_keys, collect_foreign_flow=True
            )
            metrics.update(
                {
                    k: refreshed.get(k)
                    for k in (
                        "return_5d_pct",
                        "return_10d_pct",
                        "avg_trading_value_5d",
                        "last_trading_value",
                        "volume_change",
                        "foreign_flow",
                        "institution_flow",
                    )
                }
            )
            if metrics.get("foreign_flow") is not None:
                status["flow"] = "ok"
            else:
                status["flow"] = "empty"
        except Exception as exc:
            collect_errors.append(f"metrics:{type(exc).__name__}")
            status["flow"] = "fail"
    else:
        if metrics.get("foreign_flow") is not None:
            status["flow"] = "ok"
        elif metrics:
            status["flow"] = "empty"

    recent_news: list[dict[str, Any]] = []
    recent_disclosures: list[dict[str, Any]] = []

    if collect_news:
        try:
            from data.naver_news_client import is_naver_news_configured
            from agents.weekly_watchlist_update.news_collect import (
                collect_naver_news_for_stock,
            )

            if not is_naver_news_configured():
                status["news"] = "skip"
                collect_errors.append("news:not_configured")
            else:
                raw = collect_naver_news_for_stock(
                    name,
                    sector_for_news or "반도체",
                    ticker=code,
                    top_n=3,
                    max_age_days=14,
                )
                recent_news = _normalize_news_items(raw if isinstance(raw, list) else [])
                if recent_news:
                    status["news"] = "ok"
                else:
                    status["news"] = "empty"
        except Exception as exc:
            status["news"] = "fail"
            collect_errors.append(f"news:{type(exc).__name__}")

    if collect_disclosure:
        try:
            from data.dart_client import (
                fetch_important_disclosure_items,
                is_dart_configured,
            )

            if not is_dart_configured():
                status["disclosure"] = "skip"
                collect_errors.append("disclosure:not_configured")
            else:
                raw = fetch_important_disclosure_items(code, days=30, top_n=3)
                recent_disclosures = _normalize_disclosures(
                    raw if isinstance(raw, list) else []
                )
                if recent_disclosures:
                    status["disclosure"] = "ok"
                else:
                    status["disclosure"] = "empty"
        except Exception as exc:
            status["disclosure"] = "fail"
            collect_errors.append(f"disclosure:{type(exc).__name__}")

    ctx = {
        "ticker": code,
        "name": name,
        "sector_keys": sector_keys,
        "business_summary": str(row.get("business_summary") or ""),
        "current_price": row.get("current_price"),
        "metrics": {
            "return_5d_pct": metrics.get("return_5d_pct"),
            "return_10d_pct": metrics.get("return_10d_pct"),
            "avg_trading_value_5d": metrics.get("avg_trading_value_5d"),
            "last_trading_value": metrics.get("last_trading_value"),
            "volume_change": metrics.get("volume_change"),
            "foreign_flow": metrics.get("foreign_flow"),
            "institution_flow": metrics.get("institution_flow"),
        },
        "warnings": warnings,
        "recent_news": recent_news,
        "recent_disclosures": recent_disclosures,
        "data_availability": {
            "price": status["price"] == "ok",
            "flow": status["flow"] in ("ok", "empty"),
            "news": status["news"] in ("ok", "empty"),
            "disclosure": status["disclosure"] in ("ok", "empty"),
        },
        "collect_status": status,
        "collect_errors": collect_errors,
    }
    return ctx, status


def build_context_documents(
    ai_input_doc: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """(full_context_doc, compact_doc, collection_stats)"""
    dt = now or datetime.now(KST)
    candidates = list(ai_input_doc.get("candidates") or [])

    stocks: list[dict[str, Any]] = []
    compact_list: list[dict[str, Any]] = []

    stats = {
        "news_ok": 0,
        "news_empty": 0,
        "news_fail": 0,
        "news_skip": 0,
        "disclosure_ok": 0,
        "disclosure_empty": 0,
        "disclosure_fail": 0,
        "disclosure_skip": 0,
        "flow_ok": 0,
        "flow_empty": 0,
        "flow_fail": 0,
    }

    for i, row in enumerate(candidates):
        ctx, status = build_stock_context(row)
        stocks.append(ctx)

        sk = ctx.get("sector_keys") or []
        sector_label = SECTOR_LABELS.get(sk[0], sk[0]) if sk else ""

        compact_list.append(
            {
                "ticker": ctx["ticker"],
                "name": ctx["name"],
                "sector": sector_label,
                "business_summary": _first_sentence(ctx.get("business_summary") or ""),
                "current_price": ctx.get("current_price"),
                "return_5d_pct": ctx["metrics"].get("return_5d_pct"),
                "return_10d_pct": ctx["metrics"].get("return_10d_pct"),
                "avg_trading_value_5d": ctx["metrics"].get("avg_trading_value_5d"),
                "foreign_flow": ctx["metrics"].get("foreign_flow"),
                "institution_flow": ctx["metrics"].get("institution_flow"),
                "top_news_titles": [
                    n.get("title") for n in (ctx.get("recent_news") or [])[:2] if n.get("title")
                ],
                "top_disclosure_titles": [
                    d.get("title")
                    for d in (ctx.get("recent_disclosures") or [])[:2]
                    if d.get("title")
                ],
                "risk_notes": ctx.get("warnings", {}).get("risk_notes") or [],
                "investment_caution": bool(
                    ctx.get("warnings", {}).get("investment_caution")
                ),
            }
        )

        for key, stat_key in (
            ("news", "news"),
            ("disclosure", "disclosure"),
            ("flow", "flow"),
        ):
            st = status.get(key, "skip")
            k = f"{stat_key}_{st}"
            if k in stats:
                stats[k] += 1

        if (i + 1) % 10 == 0:
            logger.info("context progress %d/%d", i + 1, len(candidates))

    full_doc = {
        "generated_at": dt.isoformat(timespec="seconds"),
        "source": "ai_input_candidates.json",
        "selection_rule": ai_input_doc.get("selection_rule"),
        "summary": {
            "ai_input_candidate_count": len(stocks),
            **stats,
        },
        "candidates": stocks,
    }

    compact_doc = {
        "generated_at": dt.isoformat(timespec="seconds"),
        "candidate_count": len(compact_list),
        "selection_rule": ai_input_doc.get("selection_rule"),
        "candidates": compact_list,
    }

    return full_doc, compact_doc, stats


def run_build_pipeline(
    *,
    universe_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """전체 파이프라인 실행 결과 요약."""
    from data.api_env import ensure_env_loaded

    ensure_env_loaded()
    out_dir = output_dir or MOCK_DIR
    uni_path = universe_path or out_dir / "candidate_universe.json"

    universe_doc = json.loads(uni_path.read_text(encoding="utf-8"))
    ai_input_doc = build_ai_input_candidates_doc(universe_doc)
    full_doc, compact_doc, stats = build_context_documents(ai_input_doc)

    paths = {
        "ai_input_candidates": out_dir / "ai_input_candidates.json",
        "ai_candidate_context": out_dir / "ai_candidate_context.json",
        "ai_candidate_context_compact": out_dir / "ai_candidate_context_compact.json",
    }
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)

    paths["ai_input_candidates"].write_text(
        json.dumps(ai_input_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["ai_candidate_context"].write_text(
        json.dumps(full_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["ai_candidate_context_compact"].write_text(
        json.dumps(compact_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "paths": {k: str(v) for k, v in paths.items()},
        "ai_input_count": ai_input_doc["summary"]["ai_input_candidate_count"],
        "sector_counts": ai_input_doc["summary"]["sector_counts"],
        "stats": stats,
        "base_count": ai_input_doc["summary"]["base_candidate_count"],
    }
