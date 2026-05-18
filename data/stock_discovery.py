"""Dynamic KR stock discovery based on volume and foreign flow."""

from __future__ import annotations

from collections import defaultdict

from config import (
    CORE_TICKERS,
    DISCOVERY_FINAL_MAX,
    DISCOVERY_TOP_N,
    VOLUME_RATIO_INCLUDE,
)
from .models import DiscoveredStock
from .sources import (
    fetch_pykrx_market_ohlcv,
    fetch_pykrx_trading_value,
    fetch_ticker_name,
)
from .utils import dedupe_keep_order, nearest_business_day, safe_float


def _top_volume_spike_tickers(market: str, date_yyyymmdd: str, top_n: int) -> list[tuple[str, float]]:
    """Return top tickers by volume ratio inside market."""
    frame = fetch_pykrx_market_ohlcv(date_yyyymmdd, market=market)
    if frame is None or len(frame) == 0:
        return []
    avg_volume = safe_float(frame["거래량"].mean(), 0.0)
    if avg_volume <= 0:
        return []
    ratios: list[tuple[str, float]] = []
    for ticker in frame.index.tolist():
        volume = safe_float(frame.loc[ticker, "거래량"], 0.0)
        ratio = volume / avg_volume if avg_volume else 0.0
        if ratio >= VOLUME_RATIO_INCLUDE:
            ratios.append((str(ticker), ratio))
    ratios.sort(key=lambda x: x[1], reverse=True)
    return ratios[:top_n]


def _top_foreign_net_buy_tickers(date_yyyymmdd: str, top_n: int) -> list[tuple[str, float]]:
    """Return top tickers by foreign net buy value."""
    frame = fetch_pykrx_trading_value(date_yyyymmdd, market="KOSPI")
    if frame is None or len(frame) == 0 or "외국인" not in frame.columns:
        return []
    pairs: list[tuple[str, float]] = []
    sorted_frame = frame.sort_values("외국인", ascending=False)
    for ticker in sorted_frame.head(top_n).index.tolist():
        value = safe_float(sorted_frame.loc[ticker, "외국인"], 0.0)
        if value > 0:
            pairs.append((str(ticker), value))
    return pairs


def discover_dynamic_stocks() -> list[DiscoveredStock]:
    """
    Build dynamic discovery list from:
    KOSPI volume spikes + KOSDAQ volume spikes + foreign net buy + core tickers.
    """
    today = nearest_business_day()
    kospi_spikes = _top_volume_spike_tickers("KOSPI", today, DISCOVERY_TOP_N)
    kosdaq_spikes = _top_volume_spike_tickers("KOSDAQ", today, DISCOVERY_TOP_N)
    foreign_top = _top_foreign_net_buy_tickers(today, DISCOVERY_TOP_N)
    core_codes = list(CORE_TICKERS.values())

    tag_map: dict[str, list[str]] = defaultdict(list)
    volume_ratio_map: dict[str, float] = {}
    foreign_map: dict[str, float] = {}
    market_map: dict[str, str] = {}

    for ticker, ratio in kospi_spikes:
        tag_map[ticker].append("kospi_volume_spike")
        volume_ratio_map[ticker] = max(volume_ratio_map.get(ticker, 0.0), ratio)
        market_map.setdefault(ticker, "KOSPI")
    for ticker, ratio in kosdaq_spikes:
        tag_map[ticker].append("kosdaq_volume_spike")
        volume_ratio_map[ticker] = max(volume_ratio_map.get(ticker, 0.0), ratio)
        market_map.setdefault(ticker, "KOSDAQ")
    for ticker, amount in foreign_top:
        tag_map[ticker].append("foreign_net_buy_top")
        foreign_map[ticker] = amount
        market_map.setdefault(ticker, "KOSPI")
    for ticker in core_codes:
        tag_map[ticker].append("core_fixed")
        market_map.setdefault(ticker, "KOSPI")

    ordered = dedupe_keep_order(
        [item[0] for item in kospi_spikes]
        + [item[0] for item in kosdaq_spikes]
        + [item[0] for item in foreign_top]
        + core_codes
    )
    ordered = ordered[:DISCOVERY_FINAL_MAX]

    output: list[DiscoveredStock] = []
    for ticker in ordered:
        output.append(
            DiscoveredStock(
                ticker=ticker,
                name=fetch_ticker_name(ticker),
                market=market_map.get(ticker, "UNKNOWN"),
                source_tags=dedupe_keep_order(tag_map.get(ticker, [])),
                volume_ratio=round(volume_ratio_map[ticker], 2) if ticker in volume_ratio_map else None,
                foreign_net_buy=foreign_map.get(ticker),
            )
        )
    return output
