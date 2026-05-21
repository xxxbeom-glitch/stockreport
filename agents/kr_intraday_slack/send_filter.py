"""SendFilterAgent — 최종 슬랙 발송 대상."""

from __future__ import annotations

from typing import Any

from .constants import (
    MAX_MESSAGES_PER_SCAN,
    SLACK_SEND_ALLOWED,
    SLACK_SEND_FORBIDDEN,
    normalize_decision,
)
from .send_log import entry_range_changed_significantly, last_sent_entry_range, was_sent_today


def filter_for_slack_send(
    evaluated: list[dict[str, Any]],
    *,
    slot: str,
    allow_resend_on_range_change: bool = True,
    require_ai: bool = False,
    max_messages: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (to_send, skipped_log_rows).
    """
    to_send: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    limit = max_messages if max_messages is not None else MAX_MESSAGES_PER_SCAN

    for row in evaluated:
        status = normalize_decision(
            str(row.get("ai_decision") or row.get("status", ""))
        )
        ticker = str(row.get("ticker", ""))
        name = str(row.get("name", ""))
        base_log = {
            "slot": slot,
            "ticker": ticker,
            "name": name,
            "status": status,
            "current_price": row.get("current_price_fmt") or row.get("current_price"),
            "entry_range": row.get("entry_range", ""),
            "sent": False,
        }

        if require_ai and not row.get("ai_send_slack"):
            skipped.append(
                {
                    **base_log,
                    "skip_reason": row.get("ai_skip_reason") or "AI send_slack=false",
                }
            )
            continue

        if status in SLACK_SEND_FORBIDDEN or status not in SLACK_SEND_ALLOWED:
            skipped.append({**base_log, "skip_reason": f"발송 금지 상태: {status}"})
            continue

        if was_sent_today(ticker):
            old_range = last_sent_entry_range(ticker) or ""
            new_range = str(row.get("entry_range") or "")
            if allow_resend_on_range_change and entry_range_changed_significantly(old_range, new_range):
                pass
            else:
                skipped.append({**base_log, "skip_reason": "당일 이미 발송됨"})
                continue

        to_send.append({**row, "status": status, "ai_decision": status})
        if len(to_send) >= limit:
            break

    return to_send, skipped
