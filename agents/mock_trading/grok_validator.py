# -*- coding: utf-8 -*-
"""Grok 뉴스/X 검증 (live-ai 전용, 추천 종목 제거 없음)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.ai.model_config import GROK_MODEL_ID
from agents.grok_client import grok_with_web_and_x_search, with_x_search_rules
from agents.mock_trading.models import GROK_VALIDATOR_DISPLAY, GROK_VALIDATOR_KEY
import config

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

VALIDATION_LABELS = (
    "positive_support",
    "caution",
    "rumor_overheat",
    "negative_risk",
    "no_extra_signal",
)


def _targets_from_agents(agent_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for agent in agent_results:
        for rec in agent.get("recommendations") or []:
            ticker = str(rec.get("ticker", "")).zfill(6)
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            out.append({"ticker": ticker, "name": str(rec.get("name") or ticker)})
    return out


def run_grok_validation(
    agent_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    if not config.GROK_API_KEY:
        return [
            {
                "status": "skipped",
                "skip_reason": "GROK_API_KEY 미설정",
                "checked_at": datetime.now(KST).isoformat(timespec="seconds"),
            }
        ], "GROK_API_KEY 미설정"

    targets = _targets_from_agents(agent_results)
    if not targets:
        return [], "검증 대상 종목 없음"

    now = datetime.now(KST).isoformat(timespec="seconds")
    validations: list[dict[str, Any]] = []

    for t in targets:
        prompt = with_x_search_rules(
            f"한국 코스닥 종목 {t['name']}({t['ticker']}) 최신 뉴스·X 반응을 검증하세요. "
            "투자 추천하지 말고 이슈만 평가. JSON만:\n"
            '{"validation_label":"positive_support|caution|rumor_overheat|negative_risk|no_extra_signal",'
            '"summary":"","positive_signals":[],"warning_signals":[],"sources_summary":[]}'
        )
        text, meta = grok_with_web_and_x_search(
            prompt,
            agent="mock_trading_grok_validator",
            model=GROK_MODEL_ID,
        )
        row: dict[str, Any] = {
            "ticker": t["ticker"],
            "name": t["name"],
            "status": "completed",
            "validation_label": "no_extra_signal",
            "summary": "",
            "positive_signals": [],
            "warning_signals": [],
            "checked_at": now,
            "sources_summary": [],
            "grok_meta": meta,
        }
        if meta.get("mode") == "error" or meta.get("error"):
            row["status"] = "skipped"
            row["skip_reason"] = str(meta.get("error") or "grok_api_error")[:200]
            validations.append(row)
            continue
        if not meta.get("web_search_used") and not meta.get("x_search_used"):
            row["status"] = "skipped"
            row["skip_reason"] = "web_or_x_search_not_used_in_response"
            validations.append(row)
            continue
        if not text:
            row["status"] = "skipped"
            row["skip_reason"] = "empty_grok_response"
            validations.append(row)
            continue
        try:
            from utils.helpers import safe_json_parse

            parsed = safe_json_parse(text)
            if isinstance(parsed, dict):
                label = str(parsed.get("validation_label") or "no_extra_signal")
                if label in VALIDATION_LABELS:
                    row["validation_label"] = label
                row["summary"] = str(parsed.get("summary") or "")[:500]
                row["positive_signals"] = list(parsed.get("positive_signals") or [])[:5]
                row["warning_signals"] = list(parsed.get("warning_signals") or [])[:5]
                row["sources_summary"] = list(parsed.get("sources_summary") or [])[:5]
        except Exception:
            row["summary"] = (text or "")[:300]
        validations.append(row)

    return validations, None
