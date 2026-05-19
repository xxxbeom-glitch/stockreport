"""KR market helpers using real pykrx calls with fallback."""

from __future__ import annotations

import contextlib
import os
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from config import DISCOVERY_TOP_N
from .kis_client import (
    get_52w_high_low as get_kis_52w,
    get_conclusion_strength,
    get_foreign_net as get_kis_foreign_net,
    get_kospi_index as get_kis_kospi,
    get_kosdaq_index as get_kis_kosdaq,
    get_price as get_kis_price,
    get_sector_trading_value as get_kis_sector_trading_value,
    get_top_volume as get_kis_top_volume,
)
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


@contextlib.contextmanager
def _suppress_pykrx_output() -> Any:
    """Suppress noisy pykrx stdout/stderr when API returns empty frames."""
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            yield


def _fetch_foreign_net_purchases_frame(
    market: str,
    date: str | None = None,
    *,
    max_lookback_days: int = 5,
) -> Any | None:
    """
    Return pykrx foreign net-purchase dataframe, or None if unavailable.

    pykrx may raise ValueError (length mismatch) or return an empty frame
    when the market is not open yet or data is not published for the date.
    """
    if pykrx_stock is None:
        return None

    base = datetime.strptime(date or get_trading_date(), "%Y%m%d")
    for offset in range(max_lookback_days + 1):
        dt = base - timedelta(days=offset)
        if dt.weekday() >= 5:
            continue
        candidate = dt.strftime("%Y%m%d")
        frame: Any | None = None
        try:
            with _suppress_pykrx_output():
                frame = pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                    candidate, candidate, market=market, investor="외국인"
                )
        except (ValueError, Exception):
            continue
        if frame is None:
            continue
        try:
            if len(frame) == 0 or len(frame.columns) == 0:
                continue
        except Exception:
            continue
        return frame
    return None


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
    """Return KOSPI/KOSDAQ snapshots (KIS first, pykrx fallback)."""
    kospi = get_kis_kospi()
    kosdaq = get_kis_kosdaq()
    return {
        "KOSPI": kospi or _index_level("1001", "KOSPI"),
        "KOSDAQ": kosdaq or _index_level("2001", "KOSDAQ"),
    }


def get_price(ticker: str, market: str = "KOSPI") -> dict[str, Any] | None:
    """Return price snapshot for ticker (KIS first, pykrx fallback)."""
    quote = get_kis_price(ticker)
    if quote:
        w52 = get_kis_52w(ticker) or {}
        quote["high_52"] = w52.get("high_52")
        quote["low_52"] = w52.get("low_52")
        quote["source"] = "kis"
        return quote
    if pykrx_stock is None:
        return None
    date = get_trading_date()
    try:
        frame = pykrx_stock.get_market_ohlcv(date, market=market)
        if frame is not None and ticker in frame.index:
            close = safe_float(frame.loc[ticker, "종가"], 0.0)
            open_p = safe_float(frame.loc[ticker, "시가"], 0.0)
            pct = ((close - open_p) / open_p) * 100 if open_p else 0.0
            return {
                "ticker": ticker,
                "price": close,
                "change_rate": pct,
                "volume": safe_float(frame.loc[ticker, "거래량"], 0.0),
                "source": "pykrx",
            }
    except Exception:
        return None
    return None


def get_top_volume_kr(n: int = 5, market: str = "KOSPI") -> list[dict[str, Any]]:
    """Return top volume leaders (KIS first, pykrx fallback)."""
    kis_rows = get_kis_top_volume(market=market, n=n)
    if kis_rows:
        enriched: list[dict[str, Any]] = []
        for row in kis_rows:
            ticker = str(row.get("ticker", ""))
            price = row.get("price")
            w52 = get_kis_52w(ticker) if ticker else None
            low_52 = (w52 or {}).get("low_52")
            high_52 = (w52 or {}).get("high_52")
            change_rate = float(row.get("change_rate") or 0.0)
            ratio = float(row.get("volume_ratio") or 0.0)
            enriched.append(
                {
                    "ticker": ticker,
                    "name": row.get("name", ticker),
                    "market": market.upper(),
                    "price": price,
                    "volume_ratio": ratio,
                    "change_rate": change_rate,
                    "change": _fmt_pct(change_rate),
                    "is_up": change_rate >= 0,
                    "low_52": low_52,
                    "high_52": high_52,
                    "price_source": "kis",
                }
            )
        return enriched
    return get_volume_leaders(market=market, top=n)


def get_foreign_flow(market: str = "KOSPI") -> list[dict[str, Any]]:
    """Return top foreign net-buy tickers."""
    frame = _fetch_foreign_net_purchases_frame(market)
    if frame is None:
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


def get_foreign_net_by_ticker(ticker: str, market: str = "KOSPI") -> float | None:
    """Return foreign net-buy for one ticker (KIS first, pykrx fallback)."""
    kis_value = get_kis_foreign_net(ticker)
    if kis_value is not None:
        return kis_value
    if pykrx_stock is not None:
        date = get_trading_date()
        try:
            if hasattr(pykrx_stock, "get_market_trading_value_by_ticker"):
                frame = pykrx_stock.get_market_trading_value_by_ticker(date, market=market)
                if frame is not None and ticker in frame.index and "외국인" in frame.columns:
                    return safe_float(frame.loc[ticker, "외국인"], 0.0)
        except Exception:
            pass
        frame = _fetch_foreign_net_purchases_frame(market, date)
        if frame is not None and ticker in frame.index:
            value_col = "순매수거래대금" if "순매수거래대금" in frame.columns else "순매수거래량"
            if value_col in frame.columns:
                return safe_float(frame.loc[ticker, value_col], 0.0)

    return get_kis_foreign_net(ticker)


def get_stock_snapshot(ticker: str, market: str = "KOSPI") -> dict[str, Any]:
    """Return current price, 52-week range, and foreign net-buy for a ticker."""
    snapshot: dict[str, Any] = {
        "ticker": ticker,
        "price": None,
        "high_52": None,
        "low_52": None,
        "foreign_net_buy": None,
        "change_rate": None,
        "price_source": "none",
    }

    realtime = get_kis_price(ticker)
    raw = realtime.get("raw", {}) if realtime else {}
    if realtime:
        snapshot.update(
            {
                "price": safe_float(realtime.get("price"), 0.0),
                "change_rate": safe_float(realtime.get("change_rate"), 0.0),
                "high_52": safe_float(raw.get("w52_hgpr"), 0.0) or None,
                "low_52": safe_float(raw.get("w52_lwpr"), 0.0) or None,
                "price_source": "kis",
            }
        )

    if pykrx_stock is not None and not snapshot.get("price"):
        date = get_trading_date()
        try:
            frame = pykrx_stock.get_market_ohlcv(date, market=market)
            if frame is not None and ticker in frame.index:
                snapshot["price"] = safe_float(frame.loc[ticker, "종가"], 0.0) or None
                snapshot["price_source"] = "pykrx"
        except Exception:
            pass
        try:
            start = (datetime.strptime(date, "%Y%m%d") - timedelta(days=370)).strftime("%Y%m%d")
            hist = pykrx_stock.get_market_ohlcv_by_date(start, date, ticker)
            if hist is not None and len(hist) > 0:
                snapshot["high_52"] = safe_float(hist["고가"].max(), 0.0) or snapshot.get("high_52")
                snapshot["low_52"] = safe_float(hist["저가"].min(), 0.0) or snapshot.get("low_52")
        except Exception:
            pass

    snapshot["foreign_net_buy"] = get_foreign_net_by_ticker(ticker, market=market)
    if snapshot["foreign_net_buy"] is None:
        snapshot["foreign_net_buy"] = 0.0
    return snapshot


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
        realtime = get_kis_price(str(row["ticker"]))
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


def _should_skip_kis_sector(name: str) -> bool:
    """Skip KIS index/composite rows that are not pykrx industry names."""
    skip_tokens = ("코스피", "지수", "기후변화", "제외")
    return any(token in name for token in skip_tokens)


def _load_sector_stock_universe(date: str) -> dict[str, list[dict[str, Any]]] | None:
    """Build {업종명: [{ticker, name, change_rate, trading_value}, ...]} from pykrx."""
    if pykrx_stock is None:
        return None

    by_sector: dict[str, list[dict[str, Any]]] = {}
    for market in ("KOSPI", "KOSDAQ"):
        try:
            with _suppress_pykrx_output():
                classified = pykrx_stock.get_market_sector_classifications(date, market=market)
                ohlcv = pykrx_stock.get_market_ohlcv(date, market=market)
        except Exception:
            continue
        if classified is None or ohlcv is None or len(classified) == 0 or len(ohlcv) == 0:
            continue

        for ticker in classified.index.tolist():
            ticker = str(ticker).zfill(6)
            if ticker not in ohlcv.index:
                continue
            sector_name = str(classified.loc[ticker, "업종명"]).strip()
            if not sector_name:
                continue
            change_rate = safe_float(classified.loc[ticker, "등락률"], 0.0)
            trading_value = safe_float(ohlcv.loc[ticker, "거래대금"], 0.0)
            stock_name = str(classified.loc[ticker, "종목명"]).strip()
            price = safe_float(classified.loc[ticker, "종가"], 0.0)
            by_sector.setdefault(sector_name, []).append(
                {
                    "ticker": ticker,
                    "name": stock_name,
                    "price": price,
                    "change_rate": change_rate,
                    "trading_value": trading_value,
                }
            )
    return by_sector or None


def get_sector_top_stocks(n: int = 3) -> dict[str, list[dict[str, Any]]]:
    """Return top-n stocks by trading value for each KIS sector."""
    if n <= 0:
        return {}

    sectors = get_kis_sector_trading_value()
    if not sectors:
        return {}

    universe = _load_sector_stock_universe(get_trading_date())
    if not universe:
        return {}

    output: dict[str, list[dict[str, Any]]] = {}
    for sector in sectors:
        sector_name = str(sector.get("name", "")).strip()
        if not sector_name or _should_skip_kis_sector(sector_name):
            continue

        candidates = universe.get(sector_name)
        if not candidates:
            continue

        ranked = sorted(candidates, key=lambda x: safe_float(x.get("trading_value"), 0.0), reverse=True)
        rows: list[dict[str, Any]] = []
        for item in ranked[:n]:
            ticker = str(item.get("ticker", ""))
            change_rate = safe_float(item.get("change_rate"), 0.0)

            quote = get_kis_price(ticker) if ticker else None
            if quote and quote.get("change_rate") is not None:
                change_rate = safe_float(quote.get("change_rate"), change_rate)

            rows.append(
                {
                    "name": str(item.get("name", ticker)),
                    "change": _fmt_pct(change_rate),
                    "is_up": change_rate >= 0,
                }
            )

        if rows:
            output[sector_name] = rows

    return output


def _kr_volume_ratio(ticker: str) -> float | None:
    """20-day average volume vs today."""
    if pykrx_stock is None:
        return None
    date = get_trading_date()
    try:
        dt = datetime.strptime(date, "%Y%m%d")
        start = (dt - timedelta(days=60)).strftime("%Y%m%d")
        hist = pykrx_stock.get_market_ohlcv_by_date(start, date, ticker)
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


def _kr_per_pbr(ticker: str) -> tuple[Any, Any, Any]:
    per, pbr, foreign_ownership = None, None, None
    if pykrx_stock is None:
        return per, pbr, foreign_ownership
    date = get_trading_date()
    try:
        frame = pykrx_stock.get_market_fundamental_by_ticker(date, market="ALL")
        if frame is not None and ticker in frame.index:
            row = frame.loc[ticker]
            per = safe_float(row.get("PER"), 0.0) or None
            pbr = safe_float(row.get("PBR"), 0.0) or None
    except Exception:
        pass
    quote = get_kis_price(ticker)
    if quote:
        raw = quote.get("raw") or {}
        rate = raw.get("frgn_hldn_rate")
        if rate is not None:
            foreign_ownership = safe_float(rate, 0.0) or None
    return per, pbr, foreign_ownership


def get_watchlist_snapshots() -> dict[str, dict[str, Any]]:
    """KR_WATCHLIST 전 종목 KIS/pykrx 스냅샷 (ticker → metrics)."""
    import config

    snapshots: dict[str, dict[str, Any]] = {}
    for _theme, stocks in config.KR_WATCHLIST.items():
        for ticker, name in stocks.items():
            code = str(ticker).zfill(6)
            snap = get_stock_snapshot(code, market="KOSPI")
            per, pbr, foreign_ownership = _kr_per_pbr(code)
            strength = get_conclusion_strength(code)
            snapshots[code] = {
                "name": name,
                "price": snap.get("price"),
                "change_rate": snap.get("change_rate"),
                "volume_ratio": _kr_volume_ratio(code),
                "foreign_net": snap.get("foreign_net_buy"),
                "conclusion_strength": (strength or {}).get("strength") if strength else None,
                "per": per,
                "pbr": pbr,
                "foreign_ownership": foreign_ownership,
            }
    return snapshots


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
