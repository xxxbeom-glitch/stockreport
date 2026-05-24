"""REPLAY market data — KIS primary, pykrx fallback/verification."""

from __future__ import annotations

from contextlib import redirect_stderr
from datetime import datetime, timedelta
import io
from typing import Any

SESSION_PROBE_TICKER = "005930"

_OHLCV_CACHE: dict[tuple[str, str, str], dict[str, dict[str, int]]] = {}


def _pykrx():
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        return pykrx_stock
    except Exception:
        return None


def _kis_ready() -> bool:
    try:
        from data.kis_client import credentials_ready

        return credentials_ready()
    except Exception:
        return False


def _kis_daily_bars(ticker: str, start: str, end: str) -> list[dict[str, Any]]:
    from data.kis_client import get_daily_ohlcv_range

    return get_daily_ohlcv_range(ticker.zfill(6), start, end)


def _bars_to_date_map(bars: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for bar in bars:
        d = str(bar.get("date") or "")
        if len(d) != 8:
            continue
        out[d] = {
            "open": int(bar.get("open") or 0),
            "high": int(bar.get("high") or 0),
            "low": int(bar.get("low") or 0),
            "close": int(bar.get("close") or 0),
            "tv": int(bar.get("trading_value") or 0),
        }
    return out


def _pykrx_session_dates(start: str, end: str) -> tuple[list[str], list[str]]:
    pykrx = _pykrx()
    if pykrx is None:
        return [], ["pykrx_unavailable"]
    errors: list[str] = []
    dates: list[str] = []
    start_dt = datetime.strptime(start, "%Y%m%d")
    end_dt = datetime.strptime(end, "%Y%m%d")
    cur = start_dt
    while cur <= end_dt:
        if cur.weekday() < 5:
            candidate = cur.strftime("%Y%m%d")
            try:
                buf = io.StringIO()
                with redirect_stderr(buf):
                    frame = pykrx.get_market_ohlcv(candidate, market="KOSPI")
                if frame is not None and len(frame) > 0:
                    dates.append(candidate)
            except Exception as exc:
                errors.append(f"pykrx_session:{candidate}:{type(exc).__name__}")
        cur += timedelta(days=1)
    return dates, errors


def _kis_session_dates(start: str, end: str) -> tuple[list[str], list[str]]:
    if not _kis_ready():
        return [], ["kis_credentials_missing"]
    pad_start = (datetime.strptime(start, "%Y%m%d") - timedelta(days=14)).strftime("%Y%m%d")
    pad_end = (datetime.strptime(end, "%Y%m%d") + timedelta(days=14)).strftime("%Y%m%d")
    try:
        bars = _kis_daily_bars(SESSION_PROBE_TICKER, pad_start, pad_end)
    except Exception as exc:
        return [], [f"kis_session:{type(exc).__name__}:{exc}"]
    if not bars:
        return [], ["kis_session:empty"]
    dates = sorted(d for d in _bars_to_date_map(bars) if start <= d <= end)
    return dates, []


def list_trading_dates_result(start_yyyymmdd: str, end_yyyymmdd: str) -> dict[str, Any]:
    """
    Resolve KRX session dates in range.
    KIS (reference ticker daily chart) primary; pykrx KOSPI market OHLCV fallback.
    """
    errors: list[str] = []
    kis_dates, kis_errs = _kis_session_dates(start_yyyymmdd, end_yyyymmdd)
    errors.extend(kis_errs)
    if kis_dates:
        return {
            "ok": True,
            "dates": kis_dates,
            "primary_source": "kis_daily_chart",
            "fallback_source": None,
            "errors": errors,
        }

    pykrx_dates, pykrx_errs = _pykrx_session_dates(start_yyyymmdd, end_yyyymmdd)
    errors.extend(pykrx_errs)
    if pykrx_dates:
        return {
            "ok": True,
            "dates": pykrx_dates,
            "primary_source": "pykrx_kospi_market",
            "fallback_source": "kis_failed",
            "errors": errors,
        }

    return {
        "ok": False,
        "dates": [],
        "primary_source": None,
        "fallback_source": None,
        "errors": errors,
        "error": "trading_calendar_unavailable",
    }


def list_trading_dates(start_yyyymmdd: str, end_yyyymmdd: str) -> list[str]:
    return list_trading_dates_result(start_yyyymmdd, end_yyyymmdd).get("dates") or []


def _load_ticker_ohlcv_map(ticker: str, start: str, end: str) -> tuple[dict[str, dict[str, int]], str | None, list[str]]:
    key = (ticker.zfill(6), start, end)
    if key in _OHLCV_CACHE:
        return _OHLCV_CACHE[key], "cache", []

    errors: list[str] = []
    if _kis_ready():
        try:
            bars = _kis_daily_bars(ticker, start, end)
            if bars:
                mapped = _bars_to_date_map(bars)
                _OHLCV_CACHE[key] = mapped
                return mapped, "kis_daily_chart", errors
            errors.append("kis:empty")
        except Exception as exc:
            errors.append(f"kis:{type(exc).__name__}:{exc}")

    pykrx = _pykrx()
    if pykrx is None:
        errors.append("pykrx_unavailable")
        return {}, None, errors

    code = ticker.zfill(6)
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            frame = pykrx.get_market_ohlcv_by_date(start, end, code)
        if frame is not None and len(frame) > 0:
            mapped: dict[str, dict[str, int]] = {}
            for idx, row in frame.iterrows():
                d = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx)[:8]
                try:
                    mapped[d] = {
                        "open": int(float(row.get("시가", 0) or 0)),
                        "high": int(float(row.get("고가", 0) or 0)),
                        "low": int(float(row.get("저가", 0) or 0)),
                        "close": int(float(row.get("종가", 0) or 0)),
                        "tv": int(float(row.get("거래대금", 0) or 0)),
                    }
                except (TypeError, ValueError):
                    continue
            if mapped:
                _OHLCV_CACHE[key] = mapped
                return mapped, "pykrx_by_ticker", errors
        errors.append("pykrx:empty")
    except Exception as exc:
        errors.append(f"pykrx:{type(exc).__name__}:{exc}")

    return {}, None, errors


def ohlcv_for_ticker_date(ticker: str, trading_date: str) -> tuple[dict[str, int] | None, str | None, list[str]]:
    start = (datetime.strptime(trading_date, "%Y%m%d") - timedelta(days=5)).strftime("%Y%m%d")
    end = (datetime.strptime(trading_date, "%Y%m%d") + timedelta(days=5)).strftime("%Y%m%d")
    mapped, source, errors = _load_ticker_ohlcv_map(ticker, start, end)
    row = mapped.get(trading_date)
    if row and row.get("close", 0) > 0:
        return row, source, errors
    return None, source, errors + [f"ohlcv_missing:{ticker}:{trading_date}"]


def open_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str | None, list[str]]:
    row, source, errors = ohlcv_for_ticker_date(ticker, trading_date)
    if not row:
        return None, None, errors
    op = int(row.get("open") or 0)
    if op > 0:
        return op, f"{source}_open", errors
    close = int(row.get("close") or 0)
    if close > 0:
        return close, f"{source}_close_as_open", errors
    return None, None, errors


def close_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str | None, list[str]]:
    row, source, errors = ohlcv_for_ticker_date(ticker, trading_date)
    if not row:
        return None, None, errors
    close = int(row.get("close") or 0)
    if close > 0:
        return close, f"{source}_close", errors
    return None, None, errors


def fill_price_krw(ticker: str, trading_date: str) -> tuple[int | None, str, str | None, list[str]]:
    op, src, errors = open_price_krw(ticker, trading_date)
    if op:
        return op, src or "kis_open", None, errors
    close, cerr, cerrs = close_price_krw(ticker, trading_date)
    errors = errors + cerrs
    if close:
        return close, cerr or "kis_close", None, errors
    return None, "", "ohlcv_missing", errors


def next_trading_date_after(trading_date: str) -> tuple[str | None, str | None, list[str]]:
    start_dt = datetime.strptime(trading_date, "%Y%m%d") + timedelta(days=1)
    end_dt = start_dt + timedelta(days=30)
    result = list_trading_dates_result(start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"))
    dates = result.get("dates") or []
    if dates:
        return dates[0], str(result.get("primary_source")), result.get("errors") or []
    return None, None, (result.get("errors") or []) + ["no_next_session"]


def enrich_universe_rows_kis(
    stocks: list[dict[str, Any]],
    trading_date: str,
    prev_date: str | None,
) -> dict[str, Any]:
    """Per-ticker KIS/pykrx OHLCV when bulk pykrx market load is unavailable."""
    failures: list[dict[str, str]] = []
    enriched = 0
    errors: list[str] = []
    for row in stocks:
        ticker = str(row.get("ticker", "")).zfill(6)
        day, _, errs = ohlcv_for_ticker_date(ticker, trading_date)
        errors.extend(errs[:1])
        if not day or day["close"] <= 0:
            failures.append({"ticker": ticker, "reason": "ohlcv_missing_on_as_of_date"})
            continue
        row["current_price_krw"] = day["close"]
        row["current_trading_value_krw"] = day.get("tv") or 0
        avg_tv = float(row.get("avg_trading_value_20d_krw") or 0)
        if avg_tv > 0 and day.get("tv", 0) > 0:
            row["tv_ratio_20d"] = day["tv"] / avg_tv
        if prev_date:
            prev, _, _ = ohlcv_for_ticker_date(ticker, prev_date)
            if prev and prev["close"] > 0:
                row["change_rate_pct"] = (day["close"] - prev["close"]) / prev["close"] * 100
        row.setdefault("data_sources", [])
        if "kis_historical" not in row["data_sources"]:
            row["data_sources"].append("kis_historical")
        enriched += 1
    return {
        "ok": enriched > 0 or not stocks,
        "enriched": enriched,
        "failures": failures,
        "errors": errors,
        "prev_trading_date": prev_date,
        "source": "kis_per_ticker",
    }
