# -*- coding: utf-8 -*-
"""4개 독립 종목추천 에이전트 (live-ai 전용)."""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.ai.model_config import (
    DEEPSEEK_MODEL_ID,
    GEMINI_MODEL_ID,
)
from agents.mock_trading.models import AGENT_SPECS, AgentSpec
from agents.mock_trading.recommendation_validate import (
    MISSING_DATA_MEMO,
    validate_agent_recommendations,
)
import ai_models
import config

logger = logging.getLogger(__name__)

RECOMMENDATION_JSON_SCHEMA = """
반드시 아래 JSON만 출력:
{
  "recommendations": [
    {
      "rank": 1,
      "ticker": "6자리",
      "name": "종목명",
      "sector_group": "ai_semiconductor_material_equipment|power_technology|industrial_robot_equipment",
      "entry_price": 0,
      "entry_range": "가격대 설명",
      "target_price": 0,
      "reasons": ["내부용 원문 이유1", "내부용 원문 이유2"],
      "risk_factors": ["내부용 원문 위험1"],
      "plain_reason": "초보자용 1~2문장. 왜 사람들이 살 만한지 쉬운 말로.",
      "plain_risk": "초보자용 1~2문장. 지금 사면 어떤 점이 부담인지 쉬운 말로.",
      "view_guide": "관찰·진입 판단용 1문장. 매수 확정·확신 표현 금지.",
      "confidence": "high|medium|low",
      "evidence_fields": ["사용한 필드명"],
      "missing_data_memo": "기관 수급 미수집"
    }
  ]
}
정확히 5개 recommendations. 다른 에이전트 결과 참조 금지.
반드시 후보 JSON에 있는 ticker만 사용. institution_flow는 미수집 — 사용·추정 금지.
목표가 > 진입가 (숫자). 손절가 필드는 사용하지 않음.
reasons/risk_factors는 내부용 원문, plain_reason/plain_risk/view_guide는 화면용 쉬운 말(각 1~2문장).
금융 전문 용어·확신 표현(무조건 상승 등) 금지. 손절 언급 금지.
"""


def resolve_model_id(spec: AgentSpec) -> str:
    if spec.model_resolver == "gemini_policy_pro":
        return GEMINI_MODEL_ID
    if spec.model_resolver == "gemini_flash_fallback":
        return ai_models.GEMINI_SUMMARY_FALLBACK_MODEL
    if spec.model_resolver == "deepseek_policy_vote":
        return DEEPSEEK_MODEL_ID
    return ""


def check_provider_ready(provider: str) -> tuple[bool, str]:
    if provider == "gemini":
        if config.GEMINI_API_KEY:
            return True, ""
        return False, "GEMINI_API_KEY 미설정"
    if provider == "deepseek":
        if ai_models.DEEPSEEK_API_KEY:
            return True, ""
        return False, "DEEPSEEK_API_KEY 미설정"
    if provider == "grok":
        if config.GROK_API_KEY:
            return True, ""
        return False, "GROK_API_KEY 미설정"
    return False, f"unknown provider: {provider}"


def build_agent_prompt(spec: AgentSpec, universe: list[dict[str, Any]]) -> str:
    perspective_rules = {
        "gemini_pro_conviction": (
            "공시·수주·실적·사업 연관성 등 실제 근거가 명확한 종목 우선. "
            "외국인 수급·거래대금 뒷받침 가점. 기관 수급은 미수집이므로 사용하지 말 것. "
            "단순 테마·과열 감점."
        ),
        "gemini_25_momentum": (
            "이번 주 단기 모멘텀·거래대금·거래량·가격 흐름·섹터 관심 우선. "
            "돌파 가능성은 보되 거래량 부족·악재·극단 과열 제외."
        ),
        "deepseek_balance": (
            "가격·거래대금·외국인 수급·뉴스·위험을 균형 평가. "
            "기관 수급 미수집. 단일 뉴스 의존·급등 추격·손실 위험 큰 종목 감점."
        ),
        "deepseek_mix": (
            "근거·모멘텀·균형 기준을 통합. 수익 가능성과 리스크 관리 동시 고려. "
            "다른 에이전트 목록은 보지 말 것."
        ),
    }
    rules = perspective_rules.get(spec.agent_key, spec.perspective)
    slim = []
    for c in universe:
        m = c.get("metrics") or {}
        slim.append(
            {
                "ticker": c.get("ticker"),
                "name": c.get("name"),
                "sector": c.get("sector_group"),
                "business_summary": c.get("business_summary"),
                "current_price": c.get("current_price"),
                "return_5d_pct": m.get("return_5d_pct"),
                "return_10d_pct": m.get("return_10d_pct"),
                "avg_trading_value_5d": m.get("avg_trading_value_5d"),
                "foreign_flow": m.get("foreign_flow"),
                "institution_flow": None,
                "top_news_titles": [
                    x.get("title")
                    for x in (c.get("news_context") or [])[:2]
                    if isinstance(x, dict)
                ],
                "top_disclosure_titles": [
                    x.get("title") or x.get("report_nm")
                    for x in (c.get("disclosure_context") or [])[:2]
                    if isinstance(x, dict)
                ],
                "investment_caution": (c.get("warnings") or {}).get("investment_caution"),
                "risk_notes": (c.get("warnings") or {}).get("risk_notes") or [],
            }
        )
    return (
        f"당신은 {spec.display_name} ({spec.perspective}) 한국 코스닥 모의투자 추천 에이전트입니다.\n"
        f"판단 기준: {rules}\n"
        f"데이터 제약: {MISSING_DATA_MEMO}. institution_flow는 null이며 근거로 쓰지 말 것.\n"
        f"후보 종목 JSON ({len(slim)}종):\n{json.dumps(slim, ensure_ascii=False)}\n"
        f"{RECOMMENDATION_JSON_SCHEMA}"
    )


def run_recommendation_agent(
    spec: AgentSpec,
    universe: list[dict[str, Any]],
) -> dict[str, Any]:
    """단일 에이전트 실행. 실패 시 recommendations 빈 배열 + error."""
    model_id = resolve_model_id(spec)
    ready, err = check_provider_ready(spec.provider)
    out: dict[str, Any] = {
        "agent_key": spec.agent_key,
        "display_name": spec.display_name,
        "perspective": spec.perspective,
        "provider": spec.provider,
        "model_id": model_id,
        "recommendations": [],
        "error": None,
    }
    if not ready:
        out["error"] = err
        return out
    if not universe:
        out["error"] = "후보군 비어 있음"
        return out

    prompt = build_agent_prompt(spec, universe)

    if spec.provider == "gemini":
        from agents.gemini_client import generate_gemini_json

        parsed = generate_gemini_json(
            prompt, agent=f"mock_trading_{spec.agent_key}", model=model_id
        )
    elif spec.provider == "deepseek":
        from agents.deepseek_client import generate_deepseek_json
        from ai_models import ModelTier

        parsed = generate_deepseek_json(
            prompt,
            agent=f"mock_trading_{spec.agent_key}",
            tier=ModelTier.VOTE,
        )
        if model_id != ai_models.model_for_tier(ModelTier.VOTE, engine="deepseek"):
            pass  # deepseek client uses tier; model_id recorded in out
    else:
        out["error"] = "unsupported provider"
        return out

    if not parsed or not isinstance(parsed.get("recommendations"), list):
        out["error"] = "AI JSON 파싱 실패 또는 recommendations 없음"
        return out

    allowed = {str(c.get("ticker", "")).zfill(6) for c in universe}
    names = {str(c.get("ticker", "")).zfill(6): str(c.get("name") or "") for c in universe}
    valid, val_errors = validate_agent_recommendations(
        parsed["recommendations"],
        allowed_tickers=allowed,
        name_by_ticker=names,
        max_picks=5,
    )
    out["recommendations"] = valid
    out["validation_errors"] = val_errors
    if not valid:
        out["error"] = out["error"] or "검증 통과 추천 0건"
    return out


def run_all_recommendation_agents(
    universe: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for spec in AGENT_SPECS:
        row = run_recommendation_agent(spec, universe)
        if row.get("error"):
            errors.append(f"{spec.agent_key}: {row['error']}")
        results.append(row)
    return results, errors
