"""US sector ETF scan and temperature classification."""

from __future__ import annotations

from .models import SectorSignal
from .sources import fetch_yfinance_history
from .utils import classify_sector_temperature, safe_float
from config import US_SECTOR_ETFS


def _compute_5d_return_and_volume_ratio(hist) -> tuple[float, float]:
    """Compute 5-day return and latest/avg volume ratio from history."""
    if hist is None or len(hist) < 2:
        return 0.0, 0.0
    closes = hist["Close"]
    volumes = hist["Volume"]
    first = safe_float(closes.iloc[0], 0.0)
    last = safe_float(closes.iloc[-1], 0.0)
    avg_vol = safe_float(volumes.mean(), 0.0)
    last_vol = safe_float(volumes.iloc[-1], 0.0)
    ret_5d = ((last - first) / first) * 100.0 if first else 0.0
    vol_ratio = (last_vol / avg_vol) if avg_vol else 0.0
    return ret_5d, vol_ratio


def scan_us_sector_flow() -> list[SectorSignal]:
    """Scan SPDR 11 + AI ETFs and return sorted temperature signals."""
    signals: list[SectorSignal] = []
    for sector_name, ticker in US_SECTOR_ETFS.items():
        hist = fetch_yfinance_history(ticker, period="7d")
        if hist is None or len(hist) < 2:
            continue
        ret_5d, vol_ratio = _compute_5d_return_and_volume_ratio(hist)
        temperature = classify_sector_temperature(ret_5d, vol_ratio)
        signals.append(
            SectorSignal(
                sector=sector_name,
                ticker=ticker,
                ret_5d=round(ret_5d, 2),
                vol_ratio=round(vol_ratio, 2),
                temperature=temperature,
                flow="중립",
            )
        )
    ranked = sorted(signals, key=lambda x: x.ret_5d, reverse=True)
    if not ranked:
        return []

    hot_count = min(5, len(ranked))
    cold_count = min(5, max(len(ranked) - hot_count, 0))
    cold_start = len(ranked) - cold_count
    for idx, signal in enumerate(ranked):
        if idx < hot_count:
            signal.flow = "유입"
        elif idx >= cold_start:
            signal.flow = "유출"
        else:
            signal.flow = "중립"
    return ranked
