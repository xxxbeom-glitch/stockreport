"""🌙 내일 볼 종목 — 투표·trend_score·AI 체인."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from agents.market_metrics.ohlcv_ratios import enrich_row_with_20d_ratios
from agents.market_metrics.quant_filter_evening import passes_evening_quant_filter, quant_risk_flags
from agents.weekly_watchlist_update.candidate_agents import (
    build_sector_context,
    enrich_candidate_with_votes,
)
from agents.weekly_watchlist_update.candidate_daily_scan import (
    apply_trend_to_candidates,
    load_recent_candidate_scans,
    row_to_daily_record,
    save_daily_scan,
)
from agents.weekly_watchlist_update.candidate_scanner import (
    _fetch_ohlcv_with_timeout,
    format_scan_progress_line,
)
from agents.weekly_watchlist_update.candidate_universe import list_candidate_entries
from agents.kr_intraday_slack.live_market_data import fetch_live_watchlist_row
from data.candidates.temporary_watch import upsert_candidates
from data.kr_market import get_trading_date

from .ai_chain import (
    attach_dart_new_disclosures,
    deepseek_evening_finalize,
    gemini_evening_assess,
    grok_evening_rows,
)
from .slack_message import build_tomorrow_watch_slack

logger = logging.getLogger("tomorrow_watch.pipeline")

ProgressCallback = Callable[[str], None]


@dataclass
class TomorrowWatchResult:
    as_of_date: str
    scanned: int = 0
    quant_passed: int = 0
    voted: int = 0
    trend_applied: int = 0
    gemini_selected: int = 0
    gemini_status: str = ""
    dart_new_count: int = 0
    grok_checked: int = 0
    grok_web_search_used: bool = False
    grok_x_search_used: bool = False
    deepseek_final: int = 0
    deepseek_status: str = ""
    final_picks: list[dict[str, Any]] = field(default_factory=list)
    slack_text: str = ""
    store_path: str | None = None
    vote_log: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _as_of_iso() -> str:
    raw = get_trading_date()
    if len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def run_tomorrow_watch_alert(
    *,
    scan_limit: int = 60,
    max_pick: int = 5,
    candidate_days: int = 5,
    live: bool = True,
    on_progress: ProgressCallback | None = None,
) -> TomorrowWatchResult:
    as_of = _as_of_iso()
    result = TomorrowWatchResult(as_of_date=as_of)
    entries = list_candidate_entries(
        exclude_watchlist=True,
        exclude_large_caps=True,
        exclude_preferred=True,
        scan_limit=scan_limit,
    )
    total = len(entries)
    quant_rows: list[dict[str, Any]] = []
    daily_records: list[dict[str, Any]] = []

    for idx, entry in enumerate(entries, start=1):
        result.scanned += 1
        ticker = str(entry["ticker"]).zfill(6)
        name = str(entry.get("name") or ticker)
        if on_progress:
            on_progress(format_scan_progress_line(idx, total, name, ticker))
        try:
            ohlcv, _ = _fetch_ohlcv_with_timeout(ticker, symbol=name)
        except Exception:
            continue
        if not ohlcv:
            continue
        enriched = enrich_row_with_20d_ratios(dict(entry), ohlcv)
        if not enriched:
            continue
        if live:
            live_row = fetch_live_watchlist_row(
                {"ticker": ticker, "name": name, "sector_name": entry.get("sector_name", "")}
            )
            for k in ("foreign_net_eok", "inst_net_eok", "current_price", "current_price_fmt"):
                if live_row.get(k) is not None:
                    enriched[k] = live_row[k]
        enriched.setdefault("foreign_net_eok", 0)
        enriched.setdefault("inst_net_eok", 0)
        ok, _ = passes_evening_quant_filter(enriched)
        if not ok:
            continue
        enriched["risk_flags"] = quant_risk_flags(enriched)
        metrics = {
            k: enriched[k]
            for k in (
                "return_5d_pct",
                "tv_increase",
                "near_high",
                "volume_ratio_20d",
                "trading_value_ratio_20d",
                "latest_trading_value",
                "current_price",
            )
            if k in enriched
        }
        metrics["tv_increase"] = float(enriched.get("trading_value_ratio_20d") or 0) >= 1.05
        quant_rows.append(enriched)
        daily_records.append(row_to_daily_record(enriched, as_of))

    result.quant_passed = len(quant_rows)
    if daily_records:
        save_daily_scan(as_of, daily_records)
    recent = load_recent_candidate_scans(as_of, days=candidate_days)
    voted_rows: list[dict[str, Any]] = []
    sector_ctx = build_sector_context(quant_rows) if quant_rows else {}
    for row in quant_rows:
        metrics = {k: row[k] for k in row if k.startswith("return") or "ratio" in k or k in ("tv_increase", "near_high", "latest_trading_value")}
        voted = enrich_candidate_with_votes(row, metrics, sector_context=sector_ctx)
        voted_rows.append(voted)
    voted_rows = apply_trend_to_candidates(voted_rows, recent)
    result.voted = len(voted_rows)
    result.trend_applied = sum(1 for r in voted_rows if r.get("trend_score"))
    result.vote_log = [
        {"ticker": r.get("ticker"), "vote_summary": r.get("vote_summary"), "trend_score": r.get("trend_score")}
        for r in voted_rows[:20]
    ]

    pool = [r for r in voted_rows if r.get("tier") in ("green", "yellow")]
    pool.sort(key=lambda r: (-float(r.get("trend_score") or 0), -int(r.get("score") or 0)))
    gemini_rows, gem_status = gemini_evening_assess(pool, max_pick=max_pick)
    result.gemini_status = gem_status
    result.gemini_selected = len(gemini_rows)
    if gem_status.startswith("gemini_failed"):
        result.errors.append("Gemini 단계 구현 보류 — 후보 미확정")
        gemini_rows = []

    result.dart_new_count = attach_dart_new_disclosures(gemini_rows)
    grok_rows, grok_n, grok_flags = grok_evening_rows(gemini_rows)
    result.grok_checked = grok_n
    result.grok_web_search_used = grok_flags.get("web_search_used", False)
    result.grok_x_search_used = grok_flags.get("x_search_used", False)

    final_rows, ds_status = deepseek_evening_finalize(grok_rows)
    result.deepseek_status = ds_status
    result.deepseek_final = len(final_rows)
    result.final_picks = final_rows

    if final_rows:
        for row in final_rows:
            row["vote_result"] = row.get("vote_summary")
        result.store_path = str(upsert_candidates(final_rows, selected_date=as_of))

    result.slack_text = build_tomorrow_watch_slack(
        analysis_clock="15:55 (장마감 직후)",
        picks=final_rows,
        scanned=result.scanned,
        quant_passed=result.quant_passed,
    )
    return result
