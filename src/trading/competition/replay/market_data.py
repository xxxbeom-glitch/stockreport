"""Historical market data helpers for replay (pykrx only)."""

from __future__ import annotations

from contextlib import redirect_stderr
from datetime import datetime, timedelta
import io


def _pykrx():
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        return pykrx_stock
    except Exception:
        return None


def _ohlcv_by_ticker(ticker: str, trading_date: str):
    pykrx = _pykrx()
    if pykrx is None:
        return None
    code = ticker.zfill(6)
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            frame = pykrx.get_market_ohlcv_by_date(trading_date, trading_date, code)
        if frame is not None and len(frame) > 0:
            return frame.iloc[0]
    except Exception:
        return None
    return None


def next_trading_date_after(trading_date: str) -> str | None:
    """First KRX session after trading_date with pykrx OHLCV for reference ticker."""
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
        row = _ohlcv_by_ticker("005930", candidate)
        if row is not None:
            return candidate
    return None


def open_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str | None]:
    row = _ohlcv_by_ticker(ticker, trading_date)
    if row is None:
        return None, "ohlcv_missing"
    try:
        op = int(float(row.get("시가", 0) or 0))
    except (TypeError, ValueError):
        return None, "open_parse_failed"
    if op > 0:
        return op, None
    return None, "ohlcv_missing"


def close_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str | None]:
    row = _ohlcv_by_ticker(ticker, trading_date)
    if row is None:
        return None, "ohlcv_missing"
    try:
        cl = int(float(row.get("종가", 0) or 0))
    except (TypeError, ValueError):
        return None, "close_parse_failed"
    if cl > 0:
        return cl, None
    return None, "ohlcv_missing"


def fill_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str, str | None]:
    """Return (price, source, error). Prefer session open; fallback to close."""
    op, err = open_price_krw(ticker, trading_date)
    if op:
        return op, "pykrx_open_by_ticker", None
    close, cerr = close_price_krw(ticker, trading_date)
    if close:
        return close, "pykrx_close_by_ticker", None
    return None, "", err or cerr
