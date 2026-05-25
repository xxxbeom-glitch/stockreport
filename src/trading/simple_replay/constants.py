"""SIMPLE_REPLAY constants (dashboard labels per product spec)."""

from __future__ import annotations

from typing import Final, TypedDict

INITIAL_CASH_KRW: Final[int] = 500_000
TOTAL_SEED_KRW: Final[int] = 2_000_000
DEFAULT_OBSERVATION_DAYS: Final[int] = 5
EVALUATION_HORIZONS: Final[tuple[int, ...]] = (5, 10, 20)
UI_EVALUATION_HORIZON: Final[int] = 5
MAX_ENTRY_PRICE_KRW: Final[int] = 100_000
MIN_AVG_TRADING_VALUE_KRW: Final[int] = 3_000_000_000
UNIVERSE_CAP: Final[int] = 120

TEAM_IDS: Final[tuple[str, ...]] = ("A", "B", "C", "D")

TEAM_TO_AGENT: Final[dict[str, str]] = {
    "A": "agent1",
    "B": "agent2",
    "C": "agent3",
    "D": "agent4",
}


class AgentUiMeta(TypedDict):
    team_id: str
    agent_key: str
    display_name: str
    type_label: str
    strategy_label: str
    badge_class: str


AGENT_UI: Final[dict[str, AgentUiMeta]] = {
    "A": {
        "team_id": "A",
        "agent_key": "agent1",
        "display_name": "에이전트 1호",
        "type_label": "빠른실행",
        "strategy_label": "거래대금 돌파",
        "badge_class": "speed",
    },
    "B": {
        "team_id": "B",
        "agent_key": "agent2",
        "display_name": "에이전트 2호",
        "type_label": "빠른실행",
        "strategy_label": "재료 확산",
        "badge_class": "speed",
    },
    "C": {
        "team_id": "C",
        "agent_key": "agent3",
        "display_name": "에이전트 3호",
        "type_label": "검증승인",
        "strategy_label": "수급 확인",
        "badge_class": "verify",
    },
    "D": {
        "team_id": "D",
        "agent_key": "agent4",
        "display_name": "에이전트 4호",
        "type_label": "검증승인",
        "strategy_label": "역전 회복",
        "badge_class": "verify",
    },
}

STRATEGY_HINTS: Final[dict[str, str]] = {
    "A": "거래대금 급증·가격 돌파·단기 강도",
    "B": "DART·뉴스·정책 이벤트, 선반영 여부",
    "C": "외국인/기관 수급·거래대금 지속성",
    "D": "급락/눌림 후 반등, 구조적 악재 배제",
}
