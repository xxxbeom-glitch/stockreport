"""Historical market data helpers for replay (KIS primary, pykrx fallback)."""

from __future__ import annotations

from src.trading.competition.replay import data_provider


def next_trading_date_after(trading_date: str) -> str | None:
    nxt, _, _ = data_provider.next_trading_date_after(trading_date)
    return nxt


def open_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str | None]:
    op, _, errs = data_provider.open_price_krw(ticker, trading_date)
    if op:
        return op, None
    return None, errs[-1] if errs else "ohlcv_missing"


def close_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str | None]:
    close, _, errs = data_provider.close_price_krw(ticker, trading_date)
    if close:
        return close, None
    return None, errs[-1] if errs else "ohlcv_missing"


def fill_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str, str | None]:
    """Return (price, source, error). Prefer session open; fallback to close."""
    price, source, err, _ = data_provider.fill_price_krw(ticker, trading_date)
    if price:
        return price, source, None
    return None, "", err
