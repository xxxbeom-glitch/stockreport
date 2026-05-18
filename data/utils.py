"""Utility helpers shared across data modules."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely cast a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    """Deduplicate while preserving insertion order."""
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def nearest_business_day(base: datetime | None = None) -> str:
    """Return nearest business day in YYYYMMDD format."""
    day = base or datetime.now()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.strftime("%Y%m%d")


def prior_business_day(days_back: int = 7, base: datetime | None = None) -> str:
    """Return prior business day with a simple lookback window."""
    day = (base or datetime.now()) - timedelta(days=days_back)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.strftime("%Y%m%d")


def classify_sector_temperature(ret_5d: float, vol_ratio: float) -> str:
    """Classify sector heat from return and volume ratio."""
    if ret_5d >= 2.0 and vol_ratio >= 1.3:
        return "뜨거움"
    if 0.5 <= ret_5d < 2.0:
        return "따뜻함"
    if -0.5 <= ret_5d < 0.5:
        return "보합"
    if ret_5d <= -2.0:
        return "차가움"
    return "보합"
