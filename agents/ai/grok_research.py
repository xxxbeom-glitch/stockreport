"""Grok Web Search + X Search — 최신 이슈 확인 (학습 지식만으로 답하지 않도록)."""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.ai.model_config import GROK_MODEL_ID
from agents.grok_client import grok_with_web_and_x_search

logger = logging.getLogger("ai.grok_research")


def fetch_grok_market_research(
    row: dict[str, Any],
    *,
    agent: str,
    task: str = "evening_watch",
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Web Search + X Search 활성화 Grok 호출.
    실패 시 (None, reason) — 하위 모델로 대체하지 않음.
    """
    name = row.get("name", "")
    ticker = row.get("ticker", "")
    prompt = f"""{task} 맥락에서 아래 종목의 최신 뉴스·호재·악재·시장 반응을 확인하세요.
반드시 검색 도구(Web Search, X Search)로 **오늘·최근 며칠** 정보를 확인한 뒤 답하세요.
학습 데이터만으로 추측하지 마세요. 확인 불가 시 "최신 검색 결과 없음"이라고 하세요.

종목: {name} ({ticker})
섹터: {row.get("sector_name", "")}

JSON만:
{{
  "mention_summary": "1~2문장",
  "why_now": "지금 주목 이유",
  "bull_case": "호재 요약",
  "bear_case": "악재·우려",
  "x_sentiment": "positive|neutral|negative|unknown",
  "sources_note": "검색으로 확인한 근거 한 줄"
}}"""

    text, meta = grok_with_web_and_x_search(
        prompt,
        agent=agent,
        model=GROK_MODEL_ID,
    )
    web_used = bool(meta.get("web_search_enabled")) and int(meta.get("web_search_calls") or 0) >= 0
    x_used = bool(meta.get("x_search_enabled")) and int(meta.get("x_search_calls") or 0) > 0
    meta["web_search_used"] = web_used
    meta["x_search_used"] = x_used

    if not text:
        err = str(meta.get("error") or "Grok 응답 없음")
        logger.warning("[%s] Grok research fail: %s", ticker, err)
        return None, err

    try:
        from utils.helpers import safe_json_parse

        parsed = safe_json_parse(text)
    except Exception:
        parsed = None
    if not isinstance(parsed, dict):
        return None, "Grok JSON 파싱 실패"

    ctx = {
        **parsed,
        "grok_model": GROK_MODEL_ID,
        "grok_meta": meta,
        "web_search_used": x_used or web_used,
        "x_search_used": x_used,
        "web_search_calls": meta.get("web_search_calls", 0),
        "x_search_calls": meta.get("x_search_calls", 0),
    }
    logger.info(
        "[%s] Grok OK web_search=%s x_search=%s calls web=%s x=%s",
        ticker,
        web_used,
        x_used,
        meta.get("web_search_calls"),
        meta.get("x_search_calls"),
    )
    return ctx, None
