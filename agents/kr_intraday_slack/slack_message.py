"""SlackMessageAgent — 장중 슬랙 알림 (자연스러운 말투)."""

from __future__ import annotations

from typing import Any

from .constants import FORBIDDEN_PHRASES
from .message_tone import compose_slack_message, soften_text


def _contains_forbidden(text: str) -> bool:
    lower = text.lower()
    return any(p in text or p in lower for p in FORBIDDEN_PHRASES)


def build_slack_message_from_ai(row: dict[str, Any]) -> str | None:
    """LLM 판단 → 슬랙 메시지 (발송 허용 + ai_send_slack=True)."""
    text = compose_slack_message(row)
    if not text or _contains_forbidden(text):
        return None
    return text


def build_slack_message(row: dict[str, Any]) -> str | None:
    """규칙 기반 더미 경로 — 동일 말투 템플릿."""
    if str(row.get("status", "")) not in (
        "테스트 진입 검토",
        "예약가 제안",
        "관찰 강화",
        "눌림 진입 가능",
        "수급 반전 감지",
    ):
        return None

    merged = {
        **row,
        "ai_send_slack": True,
        "ai_decision": row.get("status"),
        "ai_reason": soften_text(
            f"{row.get('sector_name', '')} 쪽에서 거래가 다시 붙는 흐름입니다."
        ),
        "ai_entry_view": "1주 테스트로 눌림 구간만 보면 됩니다.",
        "ai_cancel_condition": "가격 이탈 또는 거래 급감 시 오늘은 넘기기",
    }
    return build_slack_message_from_ai(merged)
