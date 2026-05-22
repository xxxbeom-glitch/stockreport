"""저녁: 5에이전트 투표 → Gemini → DART → Grok → DeepSeek."""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.ai.grok_research import fetch_grok_market_research
from agents.ai.model_config import DEEPSEEK_MODEL_ID, GEMINI_MODEL_ID
from agents.gemini_client import generate_gemini_json
from agents.kr_intraday_slack.llm_client import call_primary_json, is_gemini_configured
from data.candidates.dart_disclosure_tracker import (
    fetch_new_important_disclosures,
    format_dart_summary,
)

logger = logging.getLogger("tomorrow_watch.ai")

EVENING_FINAL_STATES = ("관찰 후보 등록", "보류", "제외")


def gemini_evening_assess(
    rows: list[dict[str, Any]],
    *,
    max_pick: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    """Gemini 관찰 가치·선정 이유. 실패 시 status=구현 보류."""
    if not rows:
        return [], "skip_empty"
    if not is_gemini_configured():
        return rows[:max_pick], "gemini_unconfigured"
    brief = [
        {
            "ticker": r.get("ticker"),
            "name": r.get("name"),
            "vote_summary": r.get("vote_summary"),
            "trend_score": r.get("trend_score"),
            "volume_ratio_20d": r.get("volume_ratio_20d"),
            "trading_value_ratio_20d": r.get("trading_value_ratio_20d"),
            "agent_check_line": r.get("agent_check_line"),
        }
        for r in rows[:25]
    ]
    prompt = f"""질문: 이 종목을 애프터마켓 및 다음날 오전에 확인할 신규 관찰 후보로 등록할 가치가 있는가?
모델 역할: 신규 관찰 가치·선정 이유 (매수 확정 아님).

후보:
{json.dumps(brief, ensure_ascii=False)}

JSON:
{{
  "picks": [
    {{
      "ticker": "6자리",
      "gemini_reason": "1~2문장",
      "aftermarket_priority": true|false,
      "next_day_check": "내일 확인 조건"
    }}
  ]
}}"""
    parsed = generate_gemini_json(
        prompt,
        agent="tomorrow_watch_gemini",
        model=GEMINI_MODEL_ID,
    )
    if not parsed:
        return [], "gemini_failed"
    by_t = {str(r["ticker"]).zfill(6): r for r in rows}
    out: list[dict[str, Any]] = []
    for p in parsed.get("picks") or []:
        t = str(p.get("ticker", "")).zfill(6)
        if t in by_t:
            out.append(
                {
                    **by_t[t],
                    "gemini_reason": p.get("gemini_reason", ""),
                    "aftermarket_priority": bool(p.get("aftermarket_priority")),
                    "next_day_check": p.get("next_day_check", ""),
                }
            )
    return out[:max_pick], "ok"


def attach_dart_new_disclosures(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        ticker = str(row.get("ticker", "")).zfill(6)
        new_items, had_new = fetch_new_important_disclosures(ticker, persist=True)
        if had_new:
            count += 1
            row["dart_disclosure_summary"] = format_dart_summary(new_items)
            row["dart_new_count"] = len(new_items)
        else:
            row["dart_disclosure_summary"] = ""
            row["dart_new_count"] = 0
    return count


def grok_evening_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, dict[str, bool]]:
    """Grok Web+X. meta: web/x 사용 집계."""
    web_any = False
    x_any = False
    done = 0
    for row in rows:
        ctx, err = fetch_grok_market_research(
            row,
            agent="tomorrow_watch_grok",
            task="evening_watch",
        )
        if ctx:
            row["grok_issue_summary"] = (
                ctx.get("why_now") or ctx.get("mention_summary") or ""
            ).strip()
            row["grok_bull"] = ctx.get("bull_case", "")
            row["grok_bear"] = ctx.get("bear_case", "")
            row["grok_meta"] = ctx.get("grok_meta", {})
            web_any = web_any or bool(ctx.get("web_search_used"))
            x_any = x_any or bool(ctx.get("x_search_used"))
            done += 1
        else:
            row["grok_issue_summary"] = ""
            row["grok_skip"] = err or "grok_failed"
    return rows, done, {"web_search_used": web_any, "x_search_used": x_any}


def deepseek_evening_finalize(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    if not rows:
        return [], "skip_empty"
    payload = [
        {
            "ticker": r.get("ticker"),
            "name": r.get("name"),
            "vote_summary": r.get("vote_summary"),
            "trend_score": r.get("trend_score"),
            "gemini_reason": r.get("gemini_reason"),
            "dart": r.get("dart_disclosure_summary"),
            "grok": r.get("grok_issue_summary"),
        }
        for r in rows
    ]
    prompt = f"""질문: 애프터마켓·내일 오전 관찰 후보로 등록할 가치가 있는가?
투표·trend_score·Gemini·DART·Grok을 종합해 최종 상태만 정하세요.
허용 final_status: {list(EVENING_FINAL_STATES)}
매수 확정 추천 금지.

입력:
{json.dumps(payload, ensure_ascii=False)}

JSON:
{{
  "final": [
    {{
      "ticker": "6자리",
      "final_status": "관찰 후보 등록|보류|제외",
      "deepseek_final_reason": "1~2문장",
      "risk_notes": "주의 1문장"
    }}
  ]
}}"""
    parsed, err = call_primary_json(prompt, agent="tomorrow_watch_deepseek")
    if not parsed:
        logger.warning("[TOMORROW_WATCH] DeepSeek 보류: %s", err)
        return [], f"deepseek_failed:{err}"
    by_t = {str(r["ticker"]).zfill(6): r for r in rows}
    out: list[dict[str, Any]] = []
    for item in parsed.get("final") or []:
        t = str(item.get("ticker", "")).zfill(6)
        if t not in by_t:
            continue
        status = str(item.get("final_status") or "보류")
        if status not in EVENING_FINAL_STATES:
            status = "보류"
        if status != "관찰 후보 등록":
            continue
        row = {**by_t[t]}
        row["final_status"] = status
        row["deepseek_final_reason"] = item.get("deepseek_final_reason", "")
        row["risk_notes"] = item.get("risk_notes", "")
        row["selection_reason"] = row["deepseek_final_reason"]
        out.append(row)
    return out, "ok"
