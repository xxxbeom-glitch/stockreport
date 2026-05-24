"""Trading calendar helpers for multi-day REPLAY."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.trading.competition.replay.data_provider import list_trading_dates, list_trading_dates_result


def iter_calendar_days(start_yyyymmdd: str, end_yyyymmdd: str):
    start = datetime.strptime(start_yyyymmdd, "%Y%m%d")
    end = datetime.strptime(end_yyyymmdd, "%Y%m%d")
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            yield cur.strftime("%Y%m%d")
        cur += timedelta(days=1)


def resolve_replay_dates_with_meta(
    replay_type: str,
    start_date: str,
    end_date: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    if replay_type == "smoke_1day":
        return [start_date], {"ok": True, "source": "single_day"}

    if replay_type == "short_5days":
        if end_date and end_date != start_date:
            meta = list_trading_dates_result(start_date, end_date)
            dates = meta.get("dates") or []
            return (dates[:5] if len(dates) >= 5 else dates), meta
        end = _shift_month(start_date, 1)
        meta = list_trading_dates_result(start_date, end)
        dates = meta.get("dates") or []
        return dates[:5], meta

    if replay_type == "month":
        y, m = int(start_date[:4]), int(start_date[4:6])
        if m == 12:
            month_end = f"{y}1231"
        else:
            month_end = (datetime(y, m + 1, 1) - timedelta(days=1)).strftime("%Y%m%d")
        if end_date:
            month_end = end_date
        meta = list_trading_dates_result(f"{y}{m:02d}01", month_end)
        return meta.get("dates") or [], meta

    if replay_type == "full_audit":
        from src.trading.competition.replay.period import FULL_AUDIT_END, FULL_AUDIT_START

        meta = list_trading_dates_result(FULL_AUDIT_START, FULL_AUDIT_END)
        return meta.get("dates") or [], meta

    if replay_type == "custom":
        if not end_date:
            return [start_date], {"ok": True, "source": "single_day"}
        meta = list_trading_dates_result(start_date, end_date)
        return meta.get("dates") or [], meta

    return [start_date], {"ok": True, "source": "single_day"}


def resolve_replay_dates(
    replay_type: str,
    start_date: str,
    end_date: str | None = None,
) -> list[str]:
    dates, _ = resolve_replay_dates_with_meta(replay_type, start_date, end_date)
    return dates


def _shift_month(yyyymmdd: str, months: int) -> str:
    dt = datetime.strptime(yyyymmdd, "%Y%m%d")
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return datetime(year, month, min(dt.day, 28)).strftime("%Y%m%d")
