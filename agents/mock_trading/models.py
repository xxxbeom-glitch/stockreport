# -*- coding: utf-8 -*-
"""주간 추천 파이프라인 상수·에이전트 스펙."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MAX_DISPLAY_PRICE = 59_000

SectorGroup = Literal[
    "ai_semiconductor_material_equipment",
    "power_technology",
    "industrial_robot_equipment",
]

SECTOR_GROUPS: tuple[SectorGroup, ...] = (
    "ai_semiconductor_material_equipment",
    "power_technology",
    "industrial_robot_equipment",
)

SECTOR_LABELS: dict[str, str] = {
    "ai_semiconductor_material_equipment": "AI 반도체·소재·장비",
    "power_technology": "전력·에너지 기술",
    "industrial_robot_equipment": "산업 자동화·로봇 장비",
}

# 종목명 키워드 1차 분류 (pykrx 이름 기준, 미매칭은 제외)
SECTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ai_semiconductor_material_equipment": (
        "반도체",
        "HBM",
        "패키징",
        "테스트",
        "식각",
        "증착",
        "세정",
        "쿼츠",
        "웨이퍼",
        "장비",
        "소재",
        "PCB",
        "디스플레이",
        "OLED",
        "칩",
        "파운드",
        "후공정",
        "전공정",
        "어닐링",
        "에피",
        "CMP",
        "노광",
        "스크린",
    ),
    "power_technology": (
        "전력",
        "변압",
        "원전",
        "SMR",
        "전력망",
        "에너지",
        "터빈",
        "송전",
        "배전",
        "전기",
        "발전",
        "솔루션",
        "ESS",
        "인버터",
        "전선",
    ),
    "industrial_robot_equipment": (
        "로봇",
        "감속",
        "모터",
        "자동화",
        "공작",
        "CNC",
        "산업",
        "설비",
        "FA",
        "정밀",
        "베어링",
        "리니어",
        "공정",
    ),
}

MIN_DAILY_TRADING_VALUE_WON = 50_000_000  # 유동성 필터 (거래대금 컬럼 있을 때)
MIN_AVG_TRADING_VALUE_5D_WON = 500_000_000  # 주간 후보: 최근 5일 평균 거래대금 하한
AI_INPUT_CANDIDATE_TARGET_MAX = 80  # 뉴스·AI 입력 권장 상한 (보고용)

ProviderName = Literal["gemini", "deepseek", "grok"]


@dataclass(frozen=True)
class AgentSpec:
    agent_key: str
    display_name: str
    perspective: str
    provider: ProviderName
    model_resolver: str  # policy id key — recommendation_agents에서 해석


AGENT_SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(
        agent_key="gemini_pro_conviction",
        display_name="Gemini Pro",
        perspective="근거확신형",
        provider="gemini",
        model_resolver="gemini_policy_pro",
    ),
    AgentSpec(
        agent_key="gemini_25_momentum",
        display_name="Gemini 2.5",
        perspective="단기모멘텀형",
        provider="gemini",
        model_resolver="gemini_flash_fallback",
    ),
    AgentSpec(
        agent_key="deepseek_balance",
        display_name="DeepSeek Balance",
        perspective="균형판단형",
        provider="deepseek",
        model_resolver="deepseek_policy_vote",
    ),
    AgentSpec(
        agent_key="deepseek_mix",
        display_name="DeepSeek Mix",
        perspective="통합선정형",
        provider="deepseek",
        model_resolver="deepseek_policy_vote",
    ),
)

GROK_VALIDATOR_KEY = "grok_issue_validator"
GROK_VALIDATOR_DISPLAY = "Grok Issue Check"

PLAIN_LANGUAGE_EDITOR_KEY = "plain_language_editor"
PLAIN_LANGUAGE_EDITOR_DISPLAY = "AI 쉬운 해설"
PLAIN_LANGUAGE_EDITOR_MODEL = "gemini-2.5-flash-lite"

CONSENSUS_LABELS: dict[int, str] = {
    1: "단독 추천",
    2: "2개 모델 추천",
    3: "강한 공통추천",
    4: "전체 모델 공통추천",
}


def empty_candidate(ticker: str, name: str, sector_group: str) -> dict[str, Any]:
    return {
        "ticker": ticker.zfill(6),
        "name": name,
        "market": "KOSDAQ",
        "sector_group": sector_group,
        "business_summary": "",
        "current_price": None,
        "price_updated_at": "",
        "price_source": "",
        "market_check_status": "unverified",
        "filters": {
            "business_included": False,
            "price_under_59000": False,
            "tradable": None,
            "liquidity_pass": None,
            "risk_flag": None,
            "risk_check_status": "unverified",
            "warning_flag": None,
        },
        "metrics": {
            "return_5d_pct": None,
            "return_10d_pct": None,
            "volume_change": None,
            "trading_value_change": None,
            "avg_trading_value_5d": None,
            "last_trading_value": None,
            "liquidity_rank": None,
            "foreign_flow": None,
            "institution_flow": None,
        },
        "news_context": [],
        "disclosure_context": [],
        "risk_notes": [],
    }
