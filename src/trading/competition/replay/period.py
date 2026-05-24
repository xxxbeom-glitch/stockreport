"""Fixed REPLAY full-audit calendar window."""

from __future__ import annotations

FULL_AUDIT_START: str = "20260101"
FULL_AUDIT_END: str = "20260430"
FULL_AUDIT_PERIOD_LABEL: str = "2026-01-01 ~ 2026-04-30"
FULL_AUDIT_SLACK_LABEL: str = "2026년 1~4월 AI 투자대결 최종 리포트"

_last_session_cache: str | None = None


def full_audit_last_trading_date() -> str | None:
    """Last KRX session in the fixed full-audit window."""
    global _last_session_cache
    if _last_session_cache:
        return _last_session_cache
    from src.trading.competition.replay.calendar import list_trading_dates

    dates = list_trading_dates(FULL_AUDIT_START, FULL_AUDIT_END)
    if dates:
        _last_session_cache = dates[-1]
    return _last_session_cache


def is_full_audit_complete(last_processed_date: str) -> bool:
    last = full_audit_last_trading_date()
    return bool(last and last_processed_date >= last)
