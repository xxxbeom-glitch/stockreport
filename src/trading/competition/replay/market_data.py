"""Historical market data helpers for replay (pykrx only)."""

from __future__ import annotations

from datetime import datetime, timedelta


def _pykrx():
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        return pykrx_stock
    except Exception:
        return None


def next_trading_date_after(trading_date: str) -> str | None:
    """First KRX session after trading_date with pykrx OHLCV data (skips weekends/holidays)."""
    pykrx = _pykrx()
    if pykrx is None:
        return None

    dt = datetime.strptime(trading_date, "%Y%m%d")
    try:
        from utils.helpers import is_market_holiday
    except ImportError:
        is_market_holiday = None  # type: ignore

    for offset in range(1, 20):
        nxt = dt + timedelta(days=offset)
        if nxt.weekday() >= 5:
            continue
        if is_market_holiday and is_market_holiday(nxt):
            continue
        candidate = nxt.strftime("%Y%m%d")
        try:
            frame = pykrx.get_market_ohlcv(candidate, market="KOSPI")
            if frame is not None and len(frame) > 0:
                return candidate
        except Exception:
            continue
    return None


def open_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str | None]:
    """Return (open_price, error)."""
    pykrx = _pykrx()
    if pykrx is None:
        return None, "pykrx_unavailable"
    code = ticker.zfill(6)
    for market in ("KOSPI", "KOSDAQ"):
        try:
            frame = pykrx.get_market_ohlcv(trading_date, market=market)
        except Exception:
            continue
        if frame is None or len(frame) == 0:
            continue
        for idx in frame.index:
            if str(idx).zfill(6) != code:
                continue
            row = frame.loc[idx]
            try:
                op = int(float(row.get("시가", 0) or 0))
            except (TypeError, ValueError):
                return None, "open_parse_failed"
            if op > 0:
                return op, None
    return None, "ohlcv_missing"


def close_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str | None]:
    """Return (close_price, error) for trading_date."""
    pykrx = _pykrx()
    if pykrx is None:
        return None, "pykrx_unavailable"
    code = ticker.zfill(6)
    for market in ("KOSPI", "KOSDAQ"):
        try:
            frame = pykrx.get_market_ohlcv(trading_date, market=market)
        except Exception:
            continue
        if frame is None or len(frame) == 0:
            continue
        for idx in frame.index:
            if str(idx).zfill(6) != code:
                continue
            row = frame.loc[idx]
            try:
                cl = int(float(row.get("종가", 0) or 0))
            except (TypeError, ValueError):
                return None, "close_parse_failed"
            if cl > 0:
                return cl, None
    return None, "ohlcv_missing"


def fill_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str, str | None]:
    """
    Return (price, source, error).
    Prefer next-session open; fallback to next-session close when open missing.
    """
    op, err = open_price_krw(ticker, trading_date)
    if op:
        return op, "pykrx_open", None

    close, cerr = close_price_krw(ticker, trading_date)
    if close:
        return close, "pykrx_close_next_session", None
    return None, "", err or cerr
