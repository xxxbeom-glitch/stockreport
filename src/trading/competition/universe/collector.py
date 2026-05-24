"""Pykrx-based KOSPI/KOSDAQ universe collector."""

from __future__ import annotations

import contextlib
import io
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MIN_HISTORY_DAYS = 20
MIN_HISTORY_PRESENT = 15  # require ticker in at least 15 of last 20 sessions


def _pykrx_stock() -> Any | None:
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        return pykrx_stock
    except Exception:
        return None


@contextlib.contextmanager
def _suppress_pykrx_output() -> Any:
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


def recent_trading_dates(
    end_date: str,
    count: int = MIN_HISTORY_DAYS,
    *,
    pykrx: Any | None = None,
) -> list[str]:
    """Walk backward from end_date to collect `count` weekday dates with OHLCV data."""
    pykrx = pykrx or _pykrx_stock()
    if pykrx is None:
        return _weekday_fallback(end_date, count)

    dates: list[str] = []
    dt = datetime.strptime(end_date, "%Y%m%d")
    for _ in range(count * 3):
        if len(dates) >= count:
            break
        if dt.weekday() >= 5:
            dt -= timedelta(days=1)
            continue
        candidate = dt.strftime("%Y%m%d")
        try:
            with _suppress_pykrx_output():
                frame = pykrx.get_market_ohlcv(candidate, market="KOSPI")
            if frame is not None and len(frame) > 0:
                dates.append(candidate)
        except Exception:
            pass
        dt -= timedelta(days=1)
    return sorted(dates)


def _weekday_fallback(end_date: str, count: int) -> list[str]:
    dates: list[str] = []
    dt = datetime.strptime(end_date, "%Y%m%d")
    while len(dates) < count:
        if dt.weekday() < 5:
            dates.append(dt.strftime("%Y%m%d"))
        dt -= timedelta(days=1)
    return sorted(dates)


def list_market_tickers(
    market: str,
    trading_date: str,
    *,
    pykrx: Any | None = None,
) -> tuple[list[str], str | None]:
    pykrx = pykrx or _pykrx_stock()
    if pykrx is None:
        return [], "pykrx_unavailable"
    try:
        with _suppress_pykrx_output():
            tickers = pykrx.get_market_ticker_list(trading_date, market=market)
        return [str(t).zfill(6) for t in tickers], None
    except Exception as exc:
        return [], f"pykrx_ticker_list_failed:{type(exc).__name__}"


def ticker_name(ticker: str, trading_date: str, *, pykrx: Any | None = None) -> str:
    pykrx = pykrx or _pykrx_stock()
    if pykrx is None:
        return ticker
    try:
        with _suppress_pykrx_output():
            return str(pykrx.get_market_ticker_name(ticker)).strip() or ticker
    except Exception:
        return ticker


def collect_market_ohlcv_bulk(
    trading_dates: list[str],
    market: str,
    *,
    pykrx: Any | None = None,
) -> tuple[dict[str, list[int]], dict[str, int], list[str]]:
    """
    Returns:
      tv_history: ticker -> list of daily trading values (non-zero only)
      latest_close: ticker -> latest close price
      errors: collection errors
    """
    pykrx = pykrx or _pykrx_stock()
    tv_history: dict[str, list[int]] = defaultdict(list)
    latest_close: dict[str, int] = {}
    errors: list[str] = []

    if pykrx is None:
        return {}, {}, ["pykrx_unavailable"]

    for date in trading_dates:
        try:
            with _suppress_pykrx_output():
                frame = pykrx.get_market_ohlcv(date, market=market)
        except Exception as exc:
            errors.append(f"{market}/{date}:{type(exc).__name__}")
            continue
        if frame is None or len(frame) == 0:
            errors.append(f"{market}/{date}:empty_frame")
            continue

        for ticker, row in frame.iterrows():
            code = str(ticker).zfill(6)
            try:
                close = int(float(row.get("종가", 0) or 0))
                tv = int(float(row.get("거래대금", 0) or 0))
            except (TypeError, ValueError):
                continue
            if date == trading_dates[-1] and close > 0:
                latest_close[code] = close
            if tv > 0:
                tv_history[code].append(tv)

    return dict(tv_history), latest_close, errors


def avg_trading_value_20d(tv_history: list[int]) -> Optional[int]:
    if len(tv_history) < MIN_HISTORY_PRESENT:
        return None
    window = tv_history[-MIN_HISTORY_DAYS:]
    if len(window) < MIN_HISTORY_PRESENT:
        return None
    return int(sum(window) / len(window))


def collect_all_stocks(
    trading_date: str,
    *,
    pykrx: Any | None = None,
    name_resolver: Callable[[str, str], str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Collect raw stock records for KOSPI + KOSDAQ.

    Each record includes ticker, name, market, current_price_krw, avg_trading_value_20d_krw.
    """
    pykrx = pykrx or _pykrx_stock()
    errors: list[str] = []
    if pykrx is None:
        return [], ["pykrx_unavailable"]

    dates = recent_trading_dates(trading_date, MIN_HISTORY_DAYS, pykrx=pykrx)
    if len(dates) < MIN_HISTORY_PRESENT:
        errors.append(f"insufficient_trading_dates:{len(dates)}")

    resolve = name_resolver or (lambda t, d: ticker_name(t, d, pykrx=pykrx))

    all_records: dict[str, dict[str, Any]] = {}

    for market in ("KOSPI", "KOSDAQ"):
        tickers, err = list_market_tickers(market, trading_date, pykrx=pykrx)
        if err:
            errors.append(f"{market}:{err}")
        tv_hist, latest_close, ohlcv_errors = collect_market_ohlcv_bulk(
            dates, market, pykrx=pykrx
        )
        errors.extend(ohlcv_errors)

        for code in tickers:
            name = resolve(code, trading_date)
            avg_tv = avg_trading_value_20d(tv_hist.get(code, []))
            all_records[code] = {
                "ticker": code,
                "name": name,
                "market": market,
                "current_price_krw": latest_close.get(code),
                "avg_trading_value_20d_krw": avg_tv,
                "history_days_present": len(tv_hist.get(code, [])),
                "data_sources": ["pykrx"],
            }

    return list(all_records.values()), errors
