"""오전: 투표 → Gemini → DART → Grok → DeepSeek 최종."""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.ai.grok_research import fetch_grok_market_research
from agents.ai.model_config import GEMINI_MODEL_ID
from agents.gemini_client import generate_gemini_json
from agents.kr_intraday_slack.llm_client import call_primary_json, is_gemini_configured
from agents.kr_intraday_slack.send_filter import filter_for_slack_send
from agents.weekly_watchlist_update.candidate_agents import (
    build_sector_context,
    enrich_candidate_with_votes,
    run_candidate_agent_votes,
    summarize_votes,
)
from data.candidates.dart_disclosure_tracker import (
    fetch_new_important_disclosures,
    format_dart_summary,
)

from .slack_message import build_morning_buy_slack, build_morning_buy_empty_slack

logger = logging.getLogger("morning_buy.voting")

MORNING_STATES = ("진입 검토", "조금 더 관찰", "추격 금지", "오늘은 패스")
SEND_STATES = frozenset({"진입 검토"})


def _metrics_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "return_5d_pct": row.get("return_5d_pct", 0),
        "tv_increase": float(row.get("trading_value_ratio_20d") or 0) >= 0.9,
        "near_high": float(row.get("current_price") or 0) / max(float(row.get("day_high") or 1), 1) >= 0.97,
        "volume_ratio_20d": row.get("volume_ratio_20d"),
        "trading_value_ratio_20d": row.get("trading_value_ratio_20d"),
        "latest_trading_value": row.get("trading_value"),
    }


def run_morning_voting_finalize(
    stocks: list[dict[str, Any]],
    *,
    slot: str,
    max_messages: int = 3,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """
    Returns (main_slack_message, send_rows, stats).
    """
    stats: dict[str, Any] = {
        "scanned": len(stocks),
        "quant_passed": 0,
        "voted": 0,
        "gemini_ok": 0,
        "dart_new": 0,
        "grok_ok": 0,
        "deepseek_ok": 0,
        "grok_web_search_used": False,
        "grok_x_search_used": False,
    }
    if not stocks:
        return build_morning_buy_empty_slack(slot=slot, scanned=0), [], stats

    sector_ctx = build_sector_context(
        [{**s, "return_5d_pct": 0, "tv_increase": True} for s in stocks[:10]]
    ) if len(stocks) >= 2 else {}

    voted: list[dict[str, Any]] = []
    for row in stocks:
        if not row.get("data_complete", True):
            continue
        metrics = _metrics_from_row(row)
        v = enrich_candidate_with_votes(row, metrics, sector_context=sector_ctx)
        voted.append(v)
    stats["voted"] = len(voted)

    gemini_status = "skip"
    if is_gemini_configured() and voted:
        brief = [
            {
                "ticker": r.get("ticker"),
                "name": r.get("name"),
                "vote_summary": r.get("vote_summary"),
                "volume_ratio_20d": r.get("volume_ratio_20d"),
                "trading_value_ratio_20d": r.get("trading_value_ratio_20d"),
            }
            for r in voted[:15]
        ]
        prompt = f"""질문: 이 종목은 현재 시점에 단타 진입을 검토할 만한가?
보조 판단만 JSON으로:
{{"assessments":[{{"ticker":"6자리","entry_ok":"yes|maybe|no","note":"1문장"}}]}}

{json.dumps(brief, ensure_ascii=False)}"""
        parsed = generate_gemini_json(
            prompt,
            agent="morning_buy_gemini",
            model=GEMINI_MODEL_ID,
        )
        if parsed:
            by_t = {str(r["ticker"]).zfill(6): r for r in voted}
            for a in parsed.get("assessments") or []:
                t = str(a.get("ticker", "")).zfill(6)
                if t in by_t:
                    by_t[t]["gemini_entry_note"] = a.get("note", "")
            gemini_status = "ok"
            stats["gemini_ok"] = len(parsed.get("assessments") or [])
        else:
            gemini_status = "gemini_failed"

    dart_new = 0
    for row in voted:
        items, had = fetch_new_important_disclosures(str(row.get("ticker", "")), persist=True)
        if had:
            dart_new += 1
            row["dart_disclosure_summary"] = format_dart_summary(items)
    stats["dart_new"] = dart_new

    deepseek_in: list[dict[str, Any]] = []
    for row in voted:
        vs = row.get("vote_summary") or {}
        reject = int(vs.get("reject") or 0)
        if reject >= 2:
            row["preliminary_status"] = "오늘은 패스"
            continue
        deepseek_in.append(row)

    stats["quant_passed"] = len(deepseek_in)
    payload = [
        {
            "ticker": r.get("ticker"),
            "name": r.get("name"),
            "votes": r.get("vote_summary"),
            "agent_votes": {k: v.get("vote") for k, v in (r.get("agent_votes") or {}).items()},
            "gemini": r.get("gemini_entry_note"),
            "dart": r.get("dart_disclosure_summary"),
            "entry_range": r.get("entry_range"),
            "volume_ratio_20d": r.get("volume_ratio_20d"),
            "trading_value_ratio_20d": r.get("trading_value_ratio_20d"),
        }
        for r in deepseek_in
    ]
    prompt = f"""질문: 현재 시점 단타 진입 검토.
투표·Gemini·DART를 종합. 허용 final_status: {list(MORNING_STATES)}
투표 reject 2개 이상·악재 크면 진입 검토 금지, 보수적으로.

{json.dumps(payload, ensure_ascii=False)}

JSON:
{{"final":[{{"ticker":"6자리","final_status":"...","reason":"1문장","cancel":"1문장","entry_range":"가격대"}}]}}"""
    parsed, err = call_primary_json(prompt, agent="morning_buy_deepseek")
    finalized: list[dict[str, Any]] = []
    if parsed:
        by_t = {str(r["ticker"]).zfill(6): r for r in deepseek_in}
        for item in parsed.get("final") or []:
            t = str(item.get("ticker", "")).zfill(6)
            if t not in by_t:
                continue
            status = str(item.get("final_status") or "조금 더 관찰")
            if status not in MORNING_STATES:
                status = "조금 더 관찰"
            row = {**by_t[t]}
            row["ai_decision"] = status
            row["ai_reason"] = item.get("reason", "")
            row["ai_cancel_condition"] = item.get("cancel", "")
            row["ai_send_slack"] = status in SEND_STATES
            if item.get("entry_range"):
                row["entry_range"] = item["entry_range"]
            finalized.append(row)
        stats["deepseek_ok"] = len(finalized)
    else:
        logger.warning("[MORNING_BUY] DeepSeek 보류: %s", err)
        stats["deepseek_error"] = err

    grok_targets = [r for r in finalized if r.get("ai_send_slack")]
    grok_done = 0
    for row in grok_targets:
        ctx, _ = fetch_grok_market_research(row, agent="morning_buy_grok", task="morning_entry")
        if ctx:
            row["grok_issue_summary"] = ctx.get("why_now") or ctx.get("mention_summary", "")
            row["grok_bear"] = ctx.get("bear_case", "")
            stats["grok_web_search_used"] = stats["grok_web_search_used"] or bool(
                ctx.get("web_search_used")
            )
            stats["grok_x_search_used"] = stats["grok_x_search_used"] or bool(
                ctx.get("x_search_used")
            )
            if row.get("grok_bear") and "악재" in str(row["grok_bear"]):
                row["ai_decision"] = "조금 더 관찰"
                row["ai_send_slack"] = False
            grok_done += 1
    stats["grok_ok"] = grok_done

    to_send, _ = filter_for_slack_send(
        [r for r in finalized if r.get("ai_send_slack")],
        slot=slot,
        require_ai=False,
        max_messages=max_messages,
    )
    main = build_morning_buy_slack(slot=slot, send_rows=to_send, scanned=len(stocks))
    if not to_send and stocks:
        main = build_morning_buy_empty_slack(slot=slot, scanned=len(stocks))
    return main, to_send, stats
