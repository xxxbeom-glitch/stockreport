"""KR 장중 슬랙 스캔 상수 (docs/ai_stock_slack_logic_v2)."""

from __future__ import annotations

from typing import Final

# 05_schedule.md — KST
SCAN_SLOTS: Final[dict[str, tuple[str, str]]] = {
    "0930": ("09:30", "장초반 1차 스캔"),
    "1050": ("10:50", "오전 흐름 유지 확인"),
    "1350": ("13:50", "오후 재유입 확인"),
    "1450": ("14:50", "마감 전 최종 확인"),
}

# 04_agents.md / 07_system_changes.md — 슬랙 발송 허용
SLACK_SEND_ALLOWED: Final[frozenset[str]] = frozenset(
    {
        "테스트 진입 검토",
        "예약가 제안",
        "관찰 강화",
        "눌림 진입 가능",
        "수급 반전 감지",
    }
)

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

# 02_message_goal.md — 금지 표현
FORBIDDEN_PHRASES: Final[tuple[str, ...]] = (
    "무조건 매수",
    "지금 사세요",
    "이 가격에 사세요",
    "급등 따라",
    "확실한 매수",
)

SECTOR_MOOD_VALUES: Final[tuple[str, ...]] = ("strong", "neutral", "weak")
