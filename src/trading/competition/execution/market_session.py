"""Trading session and NXT eligibility (spec §9-1, §9-2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


class SessionKind(str, Enum):
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"
    NXT = "nxt"


@dataclass(frozen=True)
class SessionContext:
    kind: SessionKind
    tradable: bool
    allows_market: bool
    allows_limit: bool
    allows_nxt: bool
    label: str


# KST windows (simplified official schedule for MVP validation)
_WINDOWS: list[tuple[SessionKind, time, time, bool, bool, bool]] = [
    (SessionKind.PRE_MARKET, time(8, 0), time(9, 0), True, True, False),
    (SessionKind.REGULAR, time(9, 0), time(15, 30), True, True, False),
    (SessionKind.AFTER_HOURS, time(15, 40), time(18, 0), True, True, False),
    (SessionKind.NXT, time(8, 0), time(20, 0), True, True, True),
]


def get_session_context(at: datetime | None = None) -> SessionContext:
    now = at.astimezone(KST) if at else datetime.now(KST)
    if now.weekday() >= 5:
        return SessionContext(
            kind=SessionKind.CLOSED,
            tradable=False,
            allows_market=False,
            allows_limit=False,
            allows_nxt=False,
            label="weekend_closed",
        )

    t = now.time()
    for kind, start, end, mkt, lim, nxt in _WINDOWS:
        if start <= t < end:
            return SessionContext(
                kind=kind,
                tradable=True,
                allows_market=mkt,
                allows_limit=lim,
                allows_nxt=nxt,
                label=kind.value,
            )
    return SessionContext(
        kind=SessionKind.CLOSED,
        tradable=False,
        allows_market=False,
        allows_limit=False,
        allows_nxt=False,
        label="outside_hours",
    )


def is_nxt_eligible(ticker: str, quote: dict[str, Any] | None = None) -> bool:
    """NXT eligible when quote/raw flag present or large-cap KOSPI/KOSDAQ liquid names."""
    if quote:
        raw = quote.get("raw") or {}
        flag = str(raw.get("nxt_tradable_yn") or raw.get("nxt_yn") or quote.get("nxt_eligible") or "")
        if flag.upper() in ("Y", "1", "TRUE"):
            return True
        if flag.upper() in ("N", "0", "FALSE"):
            return False
    # Default: not NXT unless explicitly flagged
    return bool(quote and quote.get("nxt_eligible"))


def validate_session_order(
    *,
    session: SessionContext,
    order_type: str,
    venue: str = "KRX",
    ticker: str = "",
    quote: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if not session.tradable:
        return False, "session_not_tradable"
    if order_type == "MARKET" and not session.allows_market:
        return False, "market_not_allowed_in_session"
    if order_type == "LIMIT" and not session.allows_limit:
        return False, "limit_not_allowed_in_session"
    if venue.upper() == "NXT":
        if not session.allows_nxt:
            return False, "nxt_not_allowed_in_session"
        if not is_nxt_eligible(ticker, quote):
            return False, "nxt_not_eligible_ticker"
    return True, "ok"


def is_weekly_report_window(at: datetime | None = None) -> bool:
    """Friday after last allowed session (after 20:00 KST)."""
    now = at.astimezone(KST) if at else datetime.now(KST)
    if now.weekday() != 4:
        return False
    return now.time() >= time(20, 0)
