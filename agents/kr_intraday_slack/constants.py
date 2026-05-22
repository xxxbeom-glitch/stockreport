"""KR 장중 슬랙 스캔 상수 — 단타·짧은 매매 판단 보조 (docs/ai_stock_slack_logic_v2)."""

from __future__ import annotations

from typing import Final

# 05_schedule.md — KST (자동 발송: 10:30, 13:50)
SCAN_SLOTS: Final[dict[str, tuple[str, str]]] = {
    "1030": ("10:30", "장 초반 흐름 확인 후 1차 진입 후보"),
    "1350": ("13:50", "오후 수급 변화·신규 후보 재점검"),
}

# Slack 0건 안내 제목용 (1350 = 장중·장마감 동일 슬롯)
SLOT_PHASE_LABEL: Final[dict[str, str]] = {
    "1030": "장전",
    "1350": "장중",
}

# 슬랙 발송 허용 decision (실전용 라벨)
SLACK_SEND_ALLOWED: Final[frozenset[str]] = frozenset(
    {
        "진입 검토",
        "관찰 강화",
        "눌림 확인",
        "예약가 후보",
        "수급 반전 감지",
    }
)

# LLM·규칙 엔진 구 표현 → 실전 라벨
DECISION_ALIASES: Final[dict[str, str]] = {
    "테스트 진입 검토": "진입 검토",
    "예약가 제안": "예약가 후보",
    "눌림 진입 가능": "눌림 확인",
}


def normalize_decision(decision: str) -> str:
    d = (decision or "").strip()
    return DECISION_ALIASES.get(d, d)


def slack_display_label(decision: str) -> str:
    """슬랙 제목·본문에 쓰는 실전용 라벨."""
    return normalize_decision(decision)

# 슬랙 발송 금지 (메시지 생성·발송 안 함)
SLACK_SEND_FORBIDDEN: Final[frozenset[str]] = frozenset(
    {
        "비추천",
        "진입 보류",
        "주의 필요",
        "추격매수 위험",
        "거래대금 부족",
        "수급 약함",
        "판단 애매",
        "데이터 부족",
        "관찰 유지",
    }
)

MAX_MESSAGES_PER_SCAN: Final[int] = 3
MAX_STOCKS_PER_SECTOR: Final[int] = 2

# 02_message_goal.md — 금지 표현 (매수 권유·운영/검증 메타)
FORBIDDEN_PHRASES: Final[tuple[str, ...]] = (
    "무조건",
    "무조건 매수",
    "지금 사세요",
    "매수하세요",
    "이 가격에 사세요",
    "급등 따라",
    "급등 확실",
    "확실한 매수",
    "테스트 발송",
    "드라이런",
    "dry-run",
    "dry run",
    "검증용",
)

# 슬랙 본문에만 금지 (로그에는 dry_run 등 사용 가능)
SLACK_BODY_FORBIDDEN: Final[tuple[str, ...]] = (
    "테스트",
    "드라이런",
    "검증",
    "취소 조건",
    "dry-run",
    "dry run",
)

# 여러 종목을 한 번에 postMessage 할 때 종목 블록 사이 구분선
SLACK_STOCK_SEPARATOR: Final[str] = "――――――――――"

SECTOR_MOOD_VALUES: Final[tuple[str, ...]] = ("strong", "neutral", "weak")

# Slack 「오늘 새로 볼 종목」 섹션 — decision → 티어
TIER_WATCH_NOW: Final[frozenset[str]] = frozenset(
    {
        "진입 검토",
        "수급 반전 감지",
    }
)
TIER_WAIT: Final[frozenset[str]] = frozenset(
    {
        "눌림 확인",
        "관찰 강화",
        "예약가 후보",
    }
)
