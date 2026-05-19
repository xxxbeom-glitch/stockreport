"""US market data helpers using real yfinance calls with fallback."""

from __future__ import annotations

from typing import Any

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None
from config import US_MAX_PRICE_KRW, US_SECTOR_ETFS, US_WATCHLIST
from .sector_flow import scan_us_sector_flow
from .sources import fetch_yfinance_history
from .utils import safe_float

DEFAULT_USD_KRW: float = 1500.0


US_INDEX_TICKERS: dict[str, str] = {
    "S&P500": "^GSPC",
    "NASDAQ": "^IXIC",
    "DOW": "^DJI",
    "RUSSELL2000": "^RUT",
}


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _index_snapshot(symbol: str) -> dict[str, Any]:
    if yf is None:
        return {"value": "N/A", "change": "N/A", "is_up": None}
    try:
        hist = yf.Ticker(symbol).history(period="7d")
    except Exception:
        return {"value": "N/A", "change": "N/A", "is_up": None}
    if hist is None or len(hist) < 2:
        return {"value": "N/A", "change": "N/A", "is_up": None}
    close = hist["Close"]
    prev = safe_float(close.iloc[-2], 0.0)
    last = safe_float(close.iloc[-1], 0.0)
    pct = ((last - prev) / prev) * 100 if prev else 0.0
    return {
        "value": f"{last:,.2f}",
        "change": _fmt_pct(pct),
        "is_up": pct >= 0,
    }


def get_us_indices() -> dict[str, dict[str, Any]]:
    """Return US major indices from yfinance."""
    return {name: _index_snapshot(ticker) for name, ticker in US_INDEX_TICKERS.items()}


def get_sector_temperature() -> dict[str, dict[str, Any]]:
    """Return sector temperature map based on ETF scan."""
    signals = scan_us_sector_flow()
    output: dict[str, dict[str, Any]] = {}
    for item in signals:
        output[item.sector] = {
            "ticker": item.ticker,
            "ret_5d": item.ret_5d,
            "vol_ratio": item.vol_ratio,
            "temp": item.temperature,
            "flow": item.flow,
        }
    return output


def get_indicators() -> dict[str, Any]:
    """Return simple macro indicators from yfinance symbols."""
    # DXY, US10Y, VIX, WTI crude, copper future
    symbols = {
        "dollar_index": "DX-Y.NYB",
        "us10y": "^TNX",
        "vix": "^VIX",
        "wti": "CL=F",
        "copper": "HG=F",
    }
    out: dict[str, Any] = {}
    for key, symbol in symbols.items():
        snap = _index_snapshot(symbol)
        out[key] = {
            "value": snap["value"],
            "change": snap["change"],
            "is_up": snap["is_up"],
        }
    return out


def get_top_volume_stocks(tickers: list[str], top: int = 5) -> list[dict[str, Any]]:
    """Return top US tickers by latest volume ratio."""
    rows: list[dict[str, Any]] = []
    if yf is None:
        return rows
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="7d")
        except Exception:
            continue
        if hist is None or len(hist) < 2:
            continue
        vol = hist["Volume"]
        close = hist["Close"]
        avg_vol = safe_float(vol.mean(), 0.0)
        last_vol = safe_float(vol.iloc[-1], 0.0)
        ratio = (last_vol / avg_vol) if avg_vol else 0.0
        prev = safe_float(close.iloc[-2], 0.0)
        last = safe_float(close.iloc[-1], 0.0)
        pct = ((last - prev) / prev) * 100 if prev else 0.0
        rows.append(
            {
                "ticker": ticker,
                "ratio": round(ratio, 2),
                "change": _fmt_pct(pct),
                "is_up": pct >= 0,
            }
        )
    rows.sort(key=lambda x: x["ratio"], reverse=True)
    return rows[:top]


def get_sector_etf_universe() -> dict[str, str]:
    """Expose configured US sector ETF universe."""
    return dict(US_SECTOR_ETFS)


def _watchlist_ticker_names() -> dict[str, str]:
    """Flatten US_WATCHLIST to {TICKER: display name}."""
    names: dict[str, str] = {}
    for stocks in US_WATCHLIST.values():
        for ticker, name in stocks.items():
            code = str(ticker).upper().strip()
            if code:
                names[code] = str(name).strip() or code
    return names


def _watchlist_tickers() -> list[str]:
    return list(_watchlist_ticker_names().keys())


def _fetch_usd_krw() -> float:
    """Return latest USD/KRW; fallback to DEFAULT_USD_KRW."""
    hist = fetch_yfinance_history("USDKRW=X", period="5d")
    if hist is None or len(hist) == 0:
        return DEFAULT_USD_KRW
    rate = safe_float(hist["Close"].iloc[-1], DEFAULT_USD_KRW)
    return rate if rate > 0 else DEFAULT_USD_KRW


def _optional_float(value: Any) -> float | None:
    num = safe_float(value, 0.0)
    if value is None or str(value).strip() in {"", "None", "null", "N/A"}:
        return None
    return num if num != 0.0 or str(value).strip() == "0" else None


def _usd_to_eok(usd_value: Any, usd_krw: float | None = None) -> float | None:
    """Convert USD amount to 억원 (KRW hundred-millions)."""
    amount = _optional_float(usd_value)
    if amount is None:
        return None
    rate = usd_krw if usd_krw and usd_krw > 0 else _fetch_usd_krw()
    return round(amount * rate / 100_000_000, 2)


def get_us_financials(ticker: str) -> dict[str, Any] | None:
    """Return US fundamentals from yfinance info (amounts in 억원 where noted)."""
    if yf is None:
        return None
    code = str(ticker).upper().strip()
    if not code:
        return None
    try:
        info = yf.Ticker(code).info or {}
    except Exception:
        return None
    if not info:
        return None

    usd_krw = _fetch_usd_krw()
    per = _optional_float(info.get("trailingPE"))
    pbr = _optional_float(info.get("priceToBook"))
    eps = _optional_float(info.get("trailingEps"))
    debt_ratio = _optional_float(info.get("debtToEquity"))
    revenue = _usd_to_eok(info.get("totalRevenue"), usd_krw)
    ebitda = _usd_to_eok(info.get("ebitda"), usd_krw)
    net_income = _usd_to_eok(info.get("netIncomeToCommon"), usd_krw)

    if all(v is None for v in (per, pbr, eps, debt_ratio, revenue, ebitda, net_income)):
        return None

    return {
        "ticker": code,
        "per": per,
        "pbr": pbr,
        "revenue": revenue,
        "ebitda": ebitda,
        "net_income": net_income,
        "eps": eps,
        "debt_ratio": debt_ratio,
    }


def _ticker_short_name(ticker: str) -> str:
    if yf is None:
        return ticker
    try:
        fast = yf.Ticker(ticker).fast_info
        name = getattr(fast, "short_name", None) or fast.get("shortName")  # type: ignore[attr-defined]
        if name:
            return str(name)
    except Exception:
        pass
    try:
        return str(yf.Ticker(ticker).info.get("shortName") or ticker)
    except Exception:
        return ticker


def get_top_volume_us(n: int = 5) -> list[dict[str, Any]]:
    """Return top US watchlist names by today volume / 20-day average volume."""
    if yf is None or n <= 0:
        return []

    usd_krw = _fetch_usd_krw()
    watchlist_names = _watchlist_ticker_names()
    rows: list[dict[str, Any]] = []

    for ticker in _watchlist_tickers():
        hist = fetch_yfinance_history(ticker, period="3mo")
        if hist is None or len(hist) < 22:
            continue

        vol = hist["Volume"]
        close = hist["Close"]
        today_vol = safe_float(vol.iloc[-1], 0.0)
        avg_20d = safe_float(vol.iloc[-21:-1].mean(), 0.0)
        if today_vol <= 0 or avg_20d <= 0:
            continue

        last = safe_float(close.iloc[-1], 0.0)
        prev = safe_float(close.iloc[-2], 0.0)
        change_rate = ((last - prev) / prev) * 100 if prev else 0.0
        volume_ratio = today_vol / avg_20d
        price_krw = int(round(last * usd_krw))
        if price_krw > US_MAX_PRICE_KRW:
            continue

        rows.append(
            {
                "ticker": ticker,
                "name": watchlist_names.get(ticker) or _ticker_short_name(ticker),
                "price_krw": price_krw,
                "change_rate": round(change_rate, 2),
                "volume_ratio": round(volume_ratio, 2),
                # main.py / report helpers
                "market": "US",
                "price": last,
                "price_fmt": f"{price_krw:,}원",
                "change": _fmt_pct(change_rate),
                "is_up": change_rate >= 0,
            }
        )

    rows.sort(key=lambda x: x["volume_ratio"], reverse=True)
    return rows[:n]
