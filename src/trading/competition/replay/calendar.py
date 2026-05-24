"""Trading calendar helpers for multi-day REPLAY."""

from __future__ import annotations

from datetime import datetime, timedelta


def _pykrx():
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        return pykrx_stock
    except Exception:
        return None


def _is_session_date(date_str: str) -> bool:
    pykrx = _pykrx()
    if pykrx is None:
        return False
    try:
        from contextlib import redirect_stderr
        import io

        buf = io.StringIO()
        with redirect_stderr(buf):
            frame = pykrx.get_market_ohlcv(date_str, market="KOSPI")
        return frame is not None and len(frame) > 0
    except Exception:
        return False


def iter_calendar_days(start_yyyymmdd: str, end_yyyymmdd: str):
    start = datetime.strptime(start_yyyymmdd, "%Y%m%d")
    end = datetime.strptime(end_yyyymmdd, "%Y%m%d")
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            yield cur.strftime("%Y%m%d")
        cur += timedelta(days=1)


def list_trading_dates(start_yyyymmdd: str, end_yyyymmdd: str) -> list[str]:
    out: list[str] = []
    for d in iter_calendar_days(start_yyyymmdd, end_yyyymmdd):
        if _is_session_date(d):
            out.append(d)
    return out


def resolve_replay_dates(
    replay_type: str,
    start_date: str,
    end_date: str | None = None,
) -> list[str]:
    if replay_type == "smoke_1day":
        return [start_date]

    if replay_type == "short_5days":
        if end_date and end_date != start_date:
            dates = list_trading_dates(start_date, end_date)
            return dates[:5] if len(dates) >= 5 else dates
        dates = list_trading_dates(start_date, _shift_month(start_date, 1))
        return dates[:5]

    if replay_type == "month":
        y, m = int(start_date[:4]), int(start_date[4:6])
        if m == 12:
            month_end = f"{y}1231"
        else:
            month_end = (datetime(y, m + 1, 1) - timedelta(days=1)).strftime("%Y%m%d")
        if end_date:
            month_end = end_date
        return list_trading_dates(f"{y}{m:02d}01", month_end)

    if replay_type == "full_audit":
        from src.trading.competition.replay.period import FULL_AUDIT_END, FULL_AUDIT_START

        _ = start_date, end_date
        return list_trading_dates(FULL_AUDIT_START, FULL_AUDIT_END)

    if replay_type == "custom":
        if not end_date:
            return [start_date]
        return list_trading_dates(start_date, end_date)

    return [start_date]


def _shift_month(yyyymmdd: str, months: int) -> str:
    dt = datetime.strptime(yyyymmdd, "%Y%m%d")
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return datetime(year, month, min(dt.day, 28)).strftime("%Y%m%d")
