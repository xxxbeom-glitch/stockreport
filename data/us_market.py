"""US market data helpers using real yfinance calls with fallback."""

from __future__ import annotations

from typing import Any

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None
from config import US_SECTOR_ETFS
from .sector_flow import scan_us_sector_flow
from .utils import safe_float


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


# Liquid US equities universe (exclude sector ETFs)
_US_LIQUID_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AMD", "AVGO",
    "NFLX", "CRM", "ORCL", "ADBE", "INTC", "QCOM", "TXN", "MU", "AMAT", "LRCX",
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "PYPL", "SQ", "COIN",
    "XOM", "CVX", "LLY", "UNH", "JNJ", "PFE", "MRK", "ABBV", "BMY", "NKE",
    "DIS", "UBER", "ABNB", "PLTR", "SNOW", "SHOP", "BABA", "PDD", "NIO",
]


def _is_etf_symbol(symbol: str) -> bool:
    sym = symbol.upper()
    if sym in set(US_SECTOR_ETFS.values()):
        return True
    if len(sym) <= 4 and sym.endswith(("X", "Y")) and sym.startswith(("X", "S", "V", "I")):
        return True
    return False


def get_top_volume_us(n: int = 5) -> list[dict[str, Any]]:
    """Return top US stocks by latest volume (individual equities only)."""
    if yf is None:
        return []
    rows: list[dict[str, Any]] = []
    for ticker in _US_LIQUID_UNIVERSE:
        if _is_etf_symbol(ticker):
            continue
        try:
            hist = yf.Ticker(ticker).history(period="5d")
        except Exception:
            continue
        if hist is None or len(hist) < 2:
            continue
        vol = hist["Volume"]
        close = hist["Close"]
        avg_vol = safe_float(vol.mean(), 0.0)
        last_vol = safe_float(vol.iloc[-1], 0.0)
        if avg_vol <= 0 or last_vol <= 0:
            continue
        prev = safe_float(close.iloc[-2], 0.0)
        last = safe_float(close.iloc[-1], 0.0)
        pct = ((last - prev) / prev) * 100 if prev else 0.0
        ratio = last_vol / avg_vol
        try:
            info_name = yf.Ticker(ticker).info.get("shortName") or ticker
        except Exception:
            info_name = ticker
        rows.append(
            {
                "ticker": ticker,
                "name": str(info_name),
                "market": "US",
                "price": last,
                "volume": last_vol,
                "volume_ratio": round(ratio, 2),
                "change_rate": pct,
                "change": _fmt_pct(pct),
                "is_up": pct >= 0,
            }
        )
    rows.sort(key=lambda x: (x.get("volume") or 0), reverse=True)
    top = rows[:n]
    for row in top:
        p = row.get("price")
        row["price_fmt"] = f"${p:,.2f}" if p else "N/A"
    return top
