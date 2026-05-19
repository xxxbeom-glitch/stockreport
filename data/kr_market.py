"""KR market helpers using real pykrx calls with fallback."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from config import DISCOVERY_TOP_N
from .kis_client import get_price
from .stock_discovery import discover_dynamic_stocks
from .utils import prior_business_day, safe_float

try:
    from pykrx import stock as pykrx_stock  # type: ignore
except Exception:
    pykrx_stock = None

# Ensure pykrx login env variables are available at runtime.
if pykrx_stock is not None:
    try:
        import config

        if getattr(config, "KRX_ID", ""):
            os.environ.setdefault("KRX_ID", config.KRX_ID)
        if getattr(config, "KRX_PW", ""):
            os.environ.setdefault("KRX_PW", config.KRX_PW)
    except Exception:
        pass


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def get_trading_date(base: datetime | None = None, max_lookback_days: int = 14) -> str:
    """
    Return nearest valid trading date (YYYYMMDD) for KRX.

    If today's market data is not available yet (or holiday/weekend), this
    function walks backward until pykrx returns non-empty index data.
    """
    if pykrx_stock is None:
        dt = base or datetime.now()
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        return dt.strftime("%Y%m%d")

    dt = base or datetime.now()
    for _ in range(max_lookback_days):
        if dt.weekday() >= 5:
            dt -= timedelta(days=1)
            continue
        candidate = dt.strftime("%Y%m%d")
        try:
            probe = pykrx_stock.get_index_ohlcv_by_date(candidate, candidate, "1001")
            if probe is not None and len(probe) > 0:
                return candidate
        except Exception:
            pass
        dt -= timedelta(days=1)

    # Safe fallback: last weekday if probing failed.
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y%m%d")


def _index_level(ticker: str, name: str) -> dict[str, Any]:
    if pykrx_stock is None:
        return {"name": name, "value": "N/A", "change": "N/A", "is_up": None}
    today = get_trading_date()
    today_dt = datetime.strptime(today, "%Y%m%d")
    prev = prior_business_day(days_back=7, base=today_dt)
    try:
        frame = pykrx_stock.get_index_ohlcv_by_date(prev, today, ticker)
        if frame is None or len(frame) < 2:
            return {"name": name, "value": "N/A", "change": "N/A", "is_up": None}
        close = frame["종가"]
        p = safe_float(close.iloc[-2], 0.0)
        c = safe_float(close.iloc[-1], 0.0)
        pct = ((c - p) / p) * 100 if p else 0.0
        return {"name": name, "value": f"{c:,.2f}", "change": _fmt_pct(pct), "is_up": pct >= 0}
    except Exception:
        return {"name": name, "value": "N/A", "change": "N/A", "is_up": None}


def get_kr_indices() -> dict[str, dict[str, Any]]:
    """Return KOSPI/KOSDAQ index snapshots from pykrx."""
    # KRX index ticker: 1001(KOSPI), 2001(KOSDAQ)
    return {
        "KOSPI": _index_level("1001", "KOSPI"),
        "KOSDAQ": _index_level("2001", "KOSDAQ"),
    }


def get_foreign_flow(market: str = "KOSPI") -> list[dict[str, Any]]:
    """Return top foreign net-buy tickers."""
    if pykrx_stock is None:
        return []
    date = get_trading_date()
    try:
        frame = pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
            date, date, market=market, investor="외국인"
        )
    except Exception:
        return []
    if frame is None or len(frame) == 0:
        return []
    value_col = "순매수거래량" if "순매수거래량" in frame.columns else None
    if value_col is None:
        # Fallback to the first numeric column if schema differs by pykrx version.
        numeric_cols = [c for c in frame.columns if getattr(frame[c], "dtype", None) is not None]
        if not numeric_cols:
            return []
        value_col = numeric_cols[0]
    top = frame.sort_values(value_col, ascending=False).head(10)
    out: list[dict[str, Any]] = []
    for ticker in top.index.tolist():
        value = safe_float(top.loc[ticker, value_col], 0.0)
        if value <= 0:
            continue
        out.append(
            {
                "ticker": str(ticker),
                "name": pykrx_stock.get_market_ticker_name(str(ticker)),
                "foreign_net_buy": value,
            }
        )
    return out


def get_volume_leaders(market: str = "KOSPI", top: int = 5) -> list[dict[str, Any]]:
    """Return volume spike leaders for a KR market."""
    if pykrx_stock is None:
        return []
    date = get_trading_date()
    try:
        frame = pykrx_stock.get_market_ohlcv(date, market=market)
    except Exception:
        return []
    if frame is None or len(frame) == 0:
        return []
    avg = safe_float(frame["거래량"].mean(), 0.0)
    if avg <= 0:
        return []
    rows: list[dict[str, Any]] = []
    for ticker in frame.index.tolist():
        ticker = str(ticker)
        volume = safe_float(frame.loc[ticker, "거래량"], 0.0)
        ratio = volume / avg if avg else 0.0
        close = safe_float(frame.loc[ticker, "종가"], 0.0)
        open_price = safe_float(frame.loc[ticker, "시가"], 0.0)
        pct = ((close - open_price) / open_price) * 100 if open_price else 0.0
        rows.append(
            {
                "ticker": ticker,
                "name": pykrx_stock.get_market_ticker_name(ticker),
                "ratio": round(ratio, 2),
                "change": _fmt_pct(pct),
                "is_up": pct >= 0,
                "price": close,
                "volume": volume,
                "price_source": "pykrx",
            }
        )
    rows.sort(key=lambda x: x["ratio"], reverse=True)
    leaders = rows[:top]
    for row in leaders:
        realtime = get_price(str(row["ticker"]))
        if not realtime:
            continue
        price = safe_float(realtime.get("price"), safe_float(row.get("price"), 0.0))
        change_rate = safe_float(realtime.get("change_rate"), 0.0)
        volume = safe_float(realtime.get("volume"), safe_float(row.get("volume"), 0.0))
        row.update(
            {
                "price": price,
                "volume": volume,
                "change": _fmt_pct(change_rate),
                "is_up": change_rate >= 0,
                "price_source": "kis",
            }
        )
    return leaders


def get_dynamic_targets() -> list[dict[str, Any]]:
    """Return dynamic stock candidates from discovery module."""
    discovered = discover_dynamic_stocks()
    return [
        {
            "ticker": item.ticker,
            "name": item.name,
            "market": item.market,
            "source_tags": list(item.source_tags),
            "volume_ratio": item.volume_ratio,
            "foreign_net_buy": item.foreign_net_buy,
        }
        for item in discovered
    ]


def get_sector_flow_kr() -> dict[str, list[str]]:
    """Approximate KR sector inflow/outflow from discovered tags."""
    targets = get_dynamic_targets()
    score: dict[str, int] = {}
    for item in targets[: max(DISCOVERY_TOP_N, 20)]:
        tags = item.get("source_tags", [])
        market = str(item.get("market", "UNKNOWN"))
        key = f"{market}_{'volume' if 'kospi_volume_spike' in tags or 'kosdaq_volume_spike' in tags else 'other'}"
        score[key] = score.get(key, 0) + 1
    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)
    flowing_in = [k for k, _ in ranked[:3]]
    flowing_out = [k for k, _ in ranked[-3:]] if ranked else []
    return {"flowing_in": flowing_in, "flowing_out": flowing_out}
