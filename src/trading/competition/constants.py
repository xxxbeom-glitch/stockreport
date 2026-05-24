"""AI Trading Competition — constants and team configuration."""

from __future__ import annotations

from typing import Final, TypedDict

# ── Financial defaults ──────────────────────────────────────────────
INITIAL_CASH_KRW: Final[int] = 500_000
MAX_POSITIONS_PER_TEAM: Final[int] = 3
MAX_ENTRY_PRICE_KRW: Final[int] = 100_000
MIN_AVG_TRADING_VALUE_KRW: Final[int] = 3_000_000_000  # 30억

TEAM_IDS: Final[tuple[str, ...]] = ("A", "B", "C", "D")

# ── Firestore collections (prefix avoids mock_trading collision) ─────
COLLECTION_CONFIG: Final[str] = "competition_config"
COLLECTION_ACCOUNTS: Final[str] = "competition_accounts"
COLLECTION_POSITIONS: Final[str] = "competition_positions"
COLLECTION_DECISIONS: Final[str] = "competition_decisions"
COLLECTION_ORDERS: Final[str] = "competition_orders"
COLLECTION_TRADES: Final[str] = "competition_trades"
COLLECTION_SNAPSHOTS: Final[str] = "competition_snapshots"
COLLECTION_EVENTS: Final[str] = "competition_events"
COLLECTION_NOTIFICATIONS: Final[str] = "competition_notifications"
COLLECTION_WEEKLY_REPORTS: Final[str] = "competition_weekly_reports"
COLLECTION_POST_SELL_TRACKING: Final[str] = "competition_post_sell_tracking"
COLLECTION_AI_USAGE_LOGS: Final[str] = "competition_ai_usage_logs"
# REPLAY-only Firestore (never write LIVE competition_* account collections)
COLLECTION_REPLAY_RUNS: Final[str] = "competition_replay_runs"
COLLECTION_REPLAY_CAMPAIGNS: Final[str] = "competition_replay_campaigns"
COLLECTION_REPLAY_WEEKLY_REPORTS: Final[str] = "competition_replay_weekly_reports"
COLLECTION_REPLAY_MONTHLY_REPORTS: Final[str] = "competition_replay_monthly_reports"

CONFIG_DOC_ID: Final[str] = "app"

# ── Local mirror paths ────────────────────────────────────────────────
LOCAL_DATA_DIR_NAME: Final[str] = "competition"

# ── Team metadata (dashboard labels) ───────────────────────────────────
class TeamMeta(TypedDict):
    team_id: str
    display_name: str
    type_label: str  # 빠른실행 | 검증승인
    strategy_label: str
    badge_class: str  # dashboard CSS class suffix


TEAM_TO_AGENT: Final[dict[str, str]] = {
    "A": "agent1",
    "B": "agent2",
    "C": "agent3",
    "D": "agent4",
}

TEAM_META: Final[dict[str, TeamMeta]] = {
    "A": {
        "team_id": "A",
        "display_name": "에이전트 A",
        "type_label": "빠른실행",
        "strategy_label": "거래대금·돌파",
        "badge_class": "speed",
    },
    "B": {
        "team_id": "B",
        "display_name": "에이전트 B",
        "type_label": "빠른실행",
        "strategy_label": "공시·재료확산",
        "badge_class": "speed",
    },
    "C": {
        "team_id": "C",
        "display_name": "에이전트 C",
        "type_label": "검증승인",
        "strategy_label": "수급·지속성확인",
        "badge_class": "verify",
    },
    "D": {
        "team_id": "D",
        "display_name": "에이전트 D",
        "type_label": "검증승인",
        "strategy_label": "눌림·반등회복",
        "badge_class": "verify",
    },
}

# Candidate limits per team (spec §6-3)
MAX_CANDIDATES: Final[dict[str, int]] = {"A": 5, "B": 5, "C": 5, "D": 3}

# Account status values
ACCOUNT_STATUS_ACTIVE: Final[str] = "active"
ACCOUNT_STATUS_CASH_WAIT: Final[str] = "cash_wait"
ACCOUNT_STATUS_SUSPENDED: Final[str] = "investment_suspended"

__all__ = [
    "INITIAL_CASH_KRW",
    "MAX_POSITIONS_PER_TEAM",
    "MAX_ENTRY_PRICE_KRW",
    "MIN_AVG_TRADING_VALUE_KRW",
    "TEAM_IDS",
    "COLLECTION_CONFIG",
    "COLLECTION_ACCOUNTS",
    "COLLECTION_POSITIONS",
    "COLLECTION_DECISIONS",
    "COLLECTION_ORDERS",
    "COLLECTION_TRADES",
    "COLLECTION_SNAPSHOTS",
    "COLLECTION_EVENTS",
    "COLLECTION_NOTIFICATIONS",
    "COLLECTION_WEEKLY_REPORTS",
    "COLLECTION_POST_SELL_TRACKING",
    "COLLECTION_AI_USAGE_LOGS",
    "CONFIG_DOC_ID",
    "LOCAL_DATA_DIR_NAME",
    "TEAM_META",
    "TEAM_TO_AGENT",
    "MAX_CANDIDATES",
    "ACCOUNT_STATUS_ACTIVE",
    "ACCOUNT_STATUS_CASH_WAIT",
    "ACCOUNT_STATUS_SUSPENDED",
]
