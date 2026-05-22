# -*- coding: utf-8 -*-
"""한국 거래일·정기 판단·실행 시각 계산."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.entry_types import (
    ENTRY_TYPE_BY_WEEKDAY,
    EXECUTION_SLOT_KRX_END,
    EXECUTION_SLOT_KRX_OPEN,
    EXECUTION_SLOT_NXT,
    EXECUTION_SLOT_NXT_END,
    JUDGMENT_AFTER_CLOSE,
    REGULAR_ENTRY_TYPES,
)

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def next_trading_day(from_date: date, *, max_scan: int = 14) -> date:
    """주말을 건너뛴 다음 거래일 (공휴일 미반영)."""
    d = from_date + timedelta(days=1)
    for _ in range(max_scan):
        if not is_weekend(d):
            return d
        d += timedelta(days=1)
    return d


def previous_trading_day(from_date: date, *, max_scan: int = 14) -> date:
    d = from_date - timedelta(days=1)
    for _ in range(max_scan):
        if not is_weekend(d):
            return d
        d -= timedelta(days=1)
    return d


def is_trading_day(d: date) -> bool:
    return not is_weekend(d)


def regular_entry_type_for_date(d: date) -> str | None:
    return ENTRY_TYPE_BY_WEEKDAY.get(d.weekday())


def is_regular_judgment_day(d: date | None = None) -> bool:
    d = d or now_kst().date()
    return regular_entry_type_for_date(d) is not None


def judgment_window_open(at: datetime | None = None) -> bool:
    """정규장 마감 후 15:30 이후."""
    at = at or now_kst()
    if not is_trading_day(at.date()):
        return False
    return at.time() >= time(*JUDGMENT_AFTER_CLOSE)


def has_weekend_risk(entry_type: str, execution_at: datetime) -> bool:
    if entry_type == "REGULAR_FRI_WEEKEND":
        return True
    if entry_type == "INTRADAY_ALERT":
        return execution_at.weekday() == 4
    return False


def plan_regular_execution(
    entry_type: str,
    judgment_at: datetime,
    *,
    nxt_available: bool,
) -> dict[str, Any]:
    """정기 판단 → NXT 16:00 또는 다음 거래일 09:10."""
    judgment_at = judgment_at.astimezone(KST)
    jdate = judgment_at.date()

    if nxt_available and is_trading_day(jdate):
        scheduled = datetime.combine(jdate, time(*EXECUTION_SLOT_NXT), tzinfo=KST)
        if judgment_at > scheduled:
            scheduled = judgment_at.replace(second=0, microsecond=0)
        session_end = datetime.combine(jdate, time(*EXECUTION_SLOT_NXT_END), tzinfo=KST)
        return {
            "scheduled_at": scheduled.isoformat(timespec="seconds"),
            "session_end_at": session_end.isoformat(timespec="seconds"),
            "order_market": "NXT_AFTER_MARKET",
            "execution_market": "NXT_AFTER_MARKET",
            "fallback_execution": False,
            "has_weekend_risk": has_weekend_risk(entry_type, scheduled),
        }

    exec_date = next_trading_day(jdate)
    scheduled = datetime.combine(exec_date, time(*EXECUTION_SLOT_KRX_OPEN), tzinfo=KST)
    session_end = datetime.combine(exec_date, time(*EXECUTION_SLOT_KRX_END), tzinfo=KST)
    return {
        "scheduled_at": scheduled.isoformat(timespec="seconds"),
        "session_end_at": session_end.isoformat(timespec="seconds"),
        "order_market": "KRX_REGULAR",
        "execution_market": "KRX_REGULAR",
        "fallback_execution": True,
        "has_weekend_risk": has_weekend_risk(entry_type, scheduled),
    }


def plan_intraday_execution(judgment_at: datetime | None = None) -> dict[str, Any]:
    """긴급 판단 — 당일 정규장 또는 단기 세션 내 지정가 체결 시도."""
    judgment_at = (judgment_at or now_kst()).astimezone(KST)
    jdate = judgment_at.date()
    if is_trading_day(jdate) and judgment_at.time() < time(*EXECUTION_SLOT_KRX_END):
        session_end = datetime.combine(jdate, time(*EXECUTION_SLOT_KRX_END), tzinfo=KST)
    else:
        session_end = judgment_at + timedelta(hours=4)
    return {
        "scheduled_at": judgment_at.isoformat(timespec="seconds"),
        "session_end_at": session_end.isoformat(timespec="seconds"),
        "order_market": "KRX_REGULAR",
        "execution_market": "KRX_REGULAR",
        "fallback_execution": False,
        "has_weekend_risk": has_weekend_risk("INTRADAY_ALERT", judgment_at),
    }


def resolve_regular_entry_type(
    at: datetime | None = None,
    *,
    force: str | None = None,
) -> str | None:
    if force and force in REGULAR_ENTRY_TYPES:
        return force
    return regular_entry_type_for_date((at or now_kst()).date())
