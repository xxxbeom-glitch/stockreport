"""Build watchlist scan payload for sequential agents."""

from __future__ import annotations

from typing import Any

import config
from data.kis_client import get_conclusion_strength, get_price as get_kis_price
from data.kr_market import get_stock_snapshot, get_trading_date
from data.sources import fetch_yfinance_history
from data.us_market import _fetch_usd_krw, get_us_financials

from .common import safe_float

# Watchlist theme → KIS 업종명 (KR supply filter)
KR_THEME_SECTORS: dict[str, list[str]] = {
    "반도체 소재": ["전기·전자", "화학"],
    "반도체 부품": ["전기·전자", "의료·정밀기기"],
    "반도체 장비": ["기계·장비", "전기·전자"],
    "방산·우주": ["운송장비·부품", "전기·전자"],
    "조선·기자재": ["운송장비·부품", "철강·금속", "화학"],
}

# Watchlist theme → US sector_flow / macro keyword hints
US_THEME_KEYWORDS: dict[str, list[str]] = {
    "빅테크 M7": ["빅테크", "기술", "IT"],
    "반도체": ["반도체", "기술"],
    "소프트웨어": ["클라우드", "기술", "IT"],
    "데이터센터": ["클라우드", "AI", "기술"],
    "AI 전력 인프라": ["AI", "에너지", "유틸리티", "AI인프라"],
    "하드웨어": ["기술", "통신"],
}


def _kr_volume_ratio(ticker: str, market: str = "KOSPI") -> float | None:
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception:
        return None
    date = get_trading_date()
    try:
        from datetime import datetime, timedelta

        dt = datetime.strptime(date, "%Y%m%d")
        start_dt = (dt - timedelta(days=60)).strftime("%Y%m%d")
        hist = pykrx_stock.get_market_ohlcv_by_date(start_dt, date, ticker)
        if hist is None or len(hist) < 22:
            return None
        vol = hist["거래량"]
        today = safe_float(vol.iloc[-1], 0.0)
        avg20 = safe_float(vol.iloc[-21:-1].mean(), 0.0)
        if today <= 0 or avg20 <= 0:
            return None
        return round(today / avg20, 2)
    except Exception:
        return None


def _us_volume_ratio(ticker: str) -> float | None:
    hist = fetch_yfinance_history(ticker, period="3mo")
    if hist is None or len(hist) < 22:
        return None
    vol = hist["Volume"]
    today = safe_float(vol.iloc[-1], 0.0)
    avg20 = safe_float(vol.iloc[-21:-1].mean(), 0.0)
    if today <= 0 or avg20 <= 0:
        return None
    return round(today / avg20, 2)


def _kr_fundamentals(ticker: str) -> dict[str, Any]:
    out: dict[str, Any] = {"per": None, "pbr": None, "foreign_ownership": None}
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        date = get_trading_date()
        frame = pykrx_stock.get_market_fundamental_by_ticker(date, market="ALL")
        if frame is not None and ticker in frame.index:
            row = frame.loc[ticker]
            out["per"] = safe_float(row.get("PER"), 0.0) or None
            out["pbr"] = safe_float(row.get("PBR"), 0.0) or None
    except Exception:
        pass
    quote = get_kis_price(ticker)
    if quote:
        raw = quote.get("raw") or {}
        rate = raw.get("frgn_hldn_rate") or raw.get("frgn_ntby_qty")
        if rate is not None:
            out["foreign_ownership"] = safe_float(rate, 0.0) or None
    return out


def _flatten_watchlist() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        from data.kr_watchlist import iter_watchlist_entries

        for entry in iter_watchlist_entries():
            ticker = str(entry.get("ticker", "")).strip()
            if not ticker:
                continue
            rows.append(
                {
                    "ticker": ticker.zfill(6),
                    "name": entry["name"],
                    "market": "KR",
                    "theme": entry["sector_name"],
                }
            )
    except Exception:
        pass
    if not rows:
        for theme, stocks in config.KR_WATCHLIST.items():
            for ticker, name in stocks.items():
                rows.append(
                    {
                        "ticker": ticker.zfill(6),
                        "name": name,
                        "market": "KR",
                        "theme": theme,
                    }
                )
    for theme, stocks in config.US_WATCHLIST.items():
        for ticker, name in stocks.items():
            rows.append(
                {
                    "ticker": ticker.upper(),
                    "name": name,
                    "market": "US",
                    "theme": theme,
                }
            )
    return rows


def build_watchlist_data(market_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Scan KR/US watchlists and attach market metrics."""
    market_data = market_data or {}
    usd_krw = _fetch_usd_krw()
    stocks: list[dict[str, Any]] = []

    for item in _flatten_watchlist():
        ticker = item["ticker"]
        market = item["market"]
        row: dict[str, Any] = {**item}

        if market == "KR":
            snap = get_stock_snapshot(ticker, market="KOSPI")
            row["price"] = snap.get("price")
            row["change_rate"] = snap.get("change_rate")
            row["low_52"] = snap.get("low_52")
            row["high_52"] = snap.get("high_52")
            row["foreign_net"] = snap.get("foreign_net_buy")
            row["volume_ratio"] = _kr_volume_ratio(ticker)
            strength = get_conclusion_strength(ticker)
            row["conclusion_strength"] = strength.get("strength") if strength else None
            fund = _kr_fundamentals(ticker)
            row.update(fund)
            try:
                from data.dart_client import fetch_disclosure_summary

                dart_summary = fetch_disclosure_summary(ticker)
                if dart_summary:
                    row["dart_summary"] = dart_summary
            except Exception:
                pass
            if row.get("price") and config.KR_MAX_PRICE is not None:
                if safe_float(row["price"]) > config.KR_MAX_PRICE:
                    continue
        else:
            hist = fetch_yfinance_history(ticker, period="3mo")
            if hist is not None and len(hist) >= 2:
                close = hist["Close"]
                row["price"] = safe_float(close.iloc[-1], 0.0)
                prev = safe_float(close.iloc[-2], 0.0)
                row["change_rate"] = ((row["price"] - prev) / prev * 100) if prev else None
                row["low_52"] = safe_float(hist["Low"].min(), 0.0) or None
                row["high_52"] = safe_float(hist["High"].max(), 0.0) or None
            else:
                row["price"] = None
                row["change_rate"] = None
                row["low_52"] = None
                row["high_52"] = None
            row["foreign_net"] = None
            row["conclusion_strength"] = None
            row["volume_ratio"] = _us_volume_ratio(ticker)
            fin = get_us_financials(ticker) or {}
            row["per"] = fin.get("per")
            row["pbr"] = fin.get("pbr")
            row["eps"] = fin.get("eps")
            row["revenue_eok"] = fin.get("revenue")
            row["ebitda_eok"] = fin.get("ebitda")
            row["net_income_eok"] = fin.get("net_income")
            row["debt_ratio"] = fin.get("debt_ratio")
            row["foreign_ownership"] = None
            price_krw = int(round(safe_float(row.get("price"), 0.0) * usd_krw))
            row["price_krw"] = price_krw if price_krw > 0 else None
            if price_krw > config.US_MAX_PRICE_KRW:
                continue

        stocks.append(row)

    return {
        "indices": market_data.get("indices") or {},
        "indicators": market_data.get("market_indicators") or market_data.get("indicators") or {},
        "sector_flow": market_data.get("sector_flow") or [],
        "stocks": stocks,
        "total_scanned": len(stocks),
    }
