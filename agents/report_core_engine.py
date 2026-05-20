"""Report Core Engine — data summary, draft, DeepSeek-based vote (03_AI_AGENTS §1–2)."""

from __future__ import annotations

import json
from typing import Any

import ai_models

from .engine_io import ReportCoreInput, ReportCoreOutput
from .fundamental import analyze_fundamental
from .llm_router import generate_draft_json
from .macro import analyze_macro
from .recommender import get_recommendations

ENGINE_ID = "report_core"


def _build_market_draft(
    indices: dict[str, Any],
    indicators: dict[str, Any],
    sector_flow: list[dict[str, Any]],
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """DeepSeek flash draft: what happened / why / key data (KR market)."""
    prompt = f"""
당신은 국장(KR) 주식 리포트 초안 작성자입니다.
아래 실데이터만 사용해 JSON만 반환하세요. 추측·신규 수치 금지.

핵심 질문:
- 무슨 일이 있었나?
- 왜 움직였나?
- 어떤 데이터가 핵심인가?

[지수]{json.dumps(indices, ensure_ascii=False)[:2500]}
[지표]{json.dumps(indicators, ensure_ascii=False)[:1500]}
[섹터흐름]{json.dumps(sector_flow[:12], ensure_ascii=False)[:1500]}

스키마:
{{
  "market_summary": "시장 3~4문장",
  "sector_highlights": ["섹터 이슈 1", "섹터 이슈 2"],
  "key_data_points": ["핵심 수치/사실 1", "핵심 수치/사실 2"]
}}
"""
    parsed, llm_meta = generate_draft_json(prompt, agent="report_core_draft", logger=logger)
    if not parsed:
        return None
    return {**parsed, "meta": {"llm": llm_meta}}


def run_report_core_engine(
    inp: ReportCoreInput,
    *,
    logger: Any = None,
    include_recommendations: bool = True,
) -> ReportCoreOutput:
    """
    Run macro (+ optional draft) and — when supply_result is present —
    fundamental vote + buy recommendations.
    """
    existing_macro = inp.get("macro_result")
    if existing_macro:
        macro = existing_macro
        draft = (macro.get("meta") or {}).get("draft")
    else:
        macro = analyze_macro(
            indices=inp["indices"],
            indicators=inp["market_indicators"],
            sector_flow=inp.get("sector_flow") or [],
            logger=logger,
        )
        draft = _build_market_draft(
            inp["indices"],
            inp["market_indicators"],
            inp.get("sector_flow") or [],
            logger=logger,
        )
        if draft:
            macro.setdefault("meta", {})["draft"] = draft

    fundamental: dict[str, Any] = {"fundamental_scores": {}, "meta": {"mode": "skipped"}}
    recommendations: dict[str, Any] = {
        "buy_recommendations": [],
        "meta": {"mode": "skipped"},
    }

    supply = inp.get("supply_result")
    wl = inp["watchlist_data"]
    if supply:
        agent_wl = {**wl, "stocks": supply.get("filtered_stocks") or wl.get("agent_stocks") or []}
        fundamental = analyze_fundamental(supply, agent_wl, logger=logger)
        if include_recommendations:
            recommendations = get_recommendations(
                macro,
                supply,
                {"momentum_scores": {}},
                fundamental,
                {"risk_assessments": {}, "one_line_summary": ""},
                wl,
                logger=logger,
            )

    meta: dict[str, Any] = {
        "engine": ENGINE_ID,
        "market_type": inp.get("market_type", "KR"),
        "models": {
            "draft": ai_models.DEEPSEEK_DRAFT_MODEL,
            "vote": ai_models.DEEPSEEK_VOTE_MODEL,
        },
    }

    out: ReportCoreOutput = {
        "engine": ENGINE_ID,
        "model": ai_models.DEEPSEEK_DRAFT_MODEL,
        "macro": macro,
        "fundamental": fundamental,
        "recommendations": recommendations,
        "meta": meta,
    }
    if draft:
        out["draft"] = draft
    return out
