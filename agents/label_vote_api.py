"""Per-stock AI label votes via API (fallback → label_vote_rules)."""

from __future__ import annotations

import json
from typing import Any

import ai_models
import config

from .deepseek_client import generate_deepseek_json
from .gemini_client import generate_gemini_json
from .grok_client import grok_x_search_json
from .label_rules import LABEL_REGRET, LABEL_TIMING, normalize_label, sanitize_label_reason
from .label_vote_helpers import stock_context_payload
from .label_vote_rules import rules_vote_deepseek, rules_vote_gemini, rules_vote_grok

_VOTE_LABELS_TEXT = f'"{LABEL_REGRET}" 또는 "{LABEL_TIMING}"'
_VOTE_SCHEMA = (
    '{"label": '
    + _VOTE_LABELS_TEXT
    + ', "reason": "최대 2줄 메모형", "confidence": 0-100}'
)


def _parse_api_vote(
    parsed: dict[str, Any] | None,
    *,
    engine: str,
    model: str,
) -> dict[str, Any] | None:
    if not parsed or not isinstance(parsed, dict):
        return None
    label = normalize_label(str(parsed.get("label", "")))
    reason = sanitize_label_reason(str(parsed.get("reason", "")))
    if not reason:
        return None
    try:
        confidence = int(parsed.get("confidence", 60))
    except (TypeError, ValueError):
        confidence = 60
    return {
        "engine": engine,
        "model": model,
        "label": label,
        "reason": reason,
        "confidence": max(0, min(100, confidence)),
        "source": "api",
    }


def _vote_prompt(role: str, stock: dict[str, Any], pipeline: dict[str, Any]) -> str:
    ctx = stock_context_payload(stock, pipeline)
    return f"""
당신은 {role}입니다.
아래 실데이터만 사용해 종목 라벨을 판단하세요. 추측·매수 권유 문구 금지.
라벨은 반드시 {_VOTE_LABELS_TEXT} 중 하나만.

[종목 데이터]
{json.dumps(ctx, ensure_ascii=False)[:3500]}

인사말 없이 JSON만:
{_VOTE_SCHEMA}
"""


def api_vote_deepseek(
    stock: dict[str, Any],
    pipeline: dict[str, Any],
    *,
    logger: Any = None,
) -> dict[str, Any]:
    if not ai_models.DEEPSEEK_API_KEY:
        return rules_vote_deepseek(stock, pipeline)
    prompt = _vote_prompt("데이터 기반 종목 분석가(DeepSeek)", stock, pipeline)
    parsed = generate_deepseek_json(
        prompt, agent="label_vote_deepseek", logger=logger, tier=ai_models.ModelTier.VOTE
    )
    vote = _parse_api_vote(parsed, engine="DeepSeek", model=ai_models.DEEPSEEK_VOTE_MODEL)
    return vote or rules_vote_deepseek(stock, pipeline)


def api_vote_grok(
    stock: dict[str, Any],
    pipeline: dict[str, Any],
    *,
    logger: Any = None,
) -> dict[str, Any]:
    if not config.GROK_API_KEY:
        return rules_vote_grok(stock, pipeline)
    prompt = _vote_prompt("시장 반응·과열감 분석가(Grok, X 검색 보조)", stock, pipeline)
    parsed, _meta = grok_x_search_json(
        prompt,
        agent="label_vote_grok",
        logger=logger,
        model=ai_models.GROK_VOTE_MODEL,
        max_output_tokens=800,
    )
    vote = _parse_api_vote(parsed, engine="Grok", model=ai_models.GROK_VOTE_MODEL)
    return vote or rules_vote_grok(stock, pipeline)


def api_vote_gemini(
    stock: dict[str, Any],
    pipeline: dict[str, Any],
    *,
    logger: Any = None,
) -> dict[str, Any]:
    if not config.GEMINI_API_KEY:
        return rules_vote_gemini(stock, pipeline)
    prompt = _vote_prompt("보수적 리스크 검수자(Gemini)", stock, pipeline)
    parsed = generate_gemini_json(
        prompt, agent="label_vote_gemini", logger=logger, tier=ai_models.ModelTier.VOTE
    )
    vote = _parse_api_vote(parsed, engine="Gemini", model=ai_models.GEMINI_RISK_MODEL)
    return vote or rules_vote_gemini(stock, pipeline)
