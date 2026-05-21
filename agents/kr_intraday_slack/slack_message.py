"""SlackMessageAgent — 섹터별 요약 슬랙 알림."""

from __future__ import annotations

from typing import Any

from .constants import FORBIDDEN_PHRASES, SCAN_SLOTS, SLACK_SEND_ALLOWED, normalize_decision
from .message_tone import (
    compose_sector_summary_message,
    contains_slack_body_forbidden,
    sanitize_slack_mrkdwn,
    soften_text,
)


def _contains_forbidden(text: str) -> bool:
    lower = text.lower()
    if contains_slack_body_forbidden(text):
        return True
    return any(p in text or p in lower for p in FORBIDDEN_PHRASES)


def build_sector_slack_summary(
    send_rows: list[dict[str, Any]],
    *,
    slot: str,
    scanned: int,
) -> str | None:
    """SendFilter 통과 종목 → 섹터별 요약 메시지 1건."""
    if not send_rows:
        return None
    clock = SCAN_SLOTS.get(slot, (slot, ""))[0]
    text = compose_sector_summary_message(
        slot_clock=clock,
        scanned=scanned,
        send_rows=send_rows,
    )
    if not text:
        return None
    text = sanitize_slack_mrkdwn(text)
    if _contains_forbidden(text):
        return None
    return text


def build_slack_message_from_ai(row: dict[str, Any]) -> str | None:
    """하위 호환 — 종목 카드만 (섹터 요약은 build_sector_slack_summary)."""
    from .message_tone import compose_sector_stock_block

    block = compose_sector_stock_block(row)
    if not block or _contains_forbidden(block):
        return None
    return block


def build_slack_message(row: dict[str, Any]) -> str | None:
    """규칙 기반 더미 경로."""
    decision = normalize_decision(str(row.get("status", "")))
    if decision not in SLACK_SEND_ALLOWED:
        return None

    merged = {
        **row,
        "ai_send_slack": True,
        "ai_decision": decision,
        "status": decision,
        "ai_reason": soften_text(
            f"{row.get('sector_name', '')} 쪽에서 거래가 다시 붙는 흐름입니다."
        ),
        "ai_entry_view": "1주 기준으로 눌림 구간만 가볍게 확인하면 됩니다.",
        "ai_cancel_condition": "가격 이탈 또는 거래 급감 시 오늘은 넘기기",
    }
    return build_slack_message_from_ai(merged)
