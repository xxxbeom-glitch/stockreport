"""SlackMessageAgent — 📡 오늘 새로 볼 종목 (단일 메인 메시지)."""

from __future__ import annotations

from typing import Any

from .constants import FORBIDDEN_PHRASES, SCAN_SLOTS
from .message_tone import (
    compose_new_candidate_scan_message,
    contains_slack_body_forbidden,
    contains_slack_ellipsis,
    has_new_candidate_scan_shape,
    sanitize_slack_mrkdwn,
    select_pass_today_rows,
    soften_text,
)


def _contains_forbidden(text: str) -> bool:
    lower = text.lower()
    if contains_slack_body_forbidden(text):
        return True
    return any(p in text or p in lower for p in FORBIDDEN_PHRASES)


def _validate_slack_text(text: str) -> str | None:
    if not text or not text.strip():
        return None
    cleaned = sanitize_slack_mrkdwn(text)
    if _contains_forbidden(cleaned) or contains_slack_ellipsis(cleaned):
        return None
    return cleaned


def build_intraday_slack_thread_bundle(
    send_rows: list[dict[str, Any]],
    *,
    slot: str,
    allow_empty: bool = False,
    pass_rows: list[dict[str, Any]] | None = None,
    evaluated: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    메인 메시지 1건 (섹터 쓰레드 없음).
    pass_rows 미지정 시 evaluated에서 🔴 후보 자동 선정.
    """
    if not send_rows and not allow_empty and not (pass_rows or evaluated):
        return None

    clock = SCAN_SLOTS.get(slot, (slot, ""))[0]
    red = list(pass_rows or [])
    if not red and evaluated:
        red = select_pass_today_rows(evaluated, send_rows)

    main = compose_new_candidate_scan_message(
        slot_clock=clock,
        send_rows=send_rows,
        pass_rows=red,
    )
    main = _validate_slack_text(main)
    if not main or not has_new_candidate_scan_shape(main):
        return None

    return {
        "main": main,
        "threads": [],
        "slot_clock": clock,
        "pass_rows": red,
    }


def build_sector_slack_summary(
    send_rows: list[dict[str, Any]],
    *,
    slot: str,
    scanned: int,
) -> str | None:
    """하위 호환 — 메인 본문만 반환."""
    del scanned
    bundle = build_intraday_slack_thread_bundle(send_rows, slot=slot, allow_empty=False)
    if bundle:
        return bundle["main"]
    return None


def build_slack_message_from_ai(row: dict[str, Any]) -> str | None:
    from .message_tone import compose_new_candidate_stock_block

    block = compose_new_candidate_stock_block(row)
    if not block or _contains_forbidden(block):
        return None
    return block


def build_slack_message(row: dict[str, Any]) -> str | None:
    """규칙 기반 더미 경로."""
    from .constants import SLACK_SEND_ALLOWED, normalize_decision

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
