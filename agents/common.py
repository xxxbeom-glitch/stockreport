"""Shared helpers for sequential agent pipeline."""

from __future__ import annotations

from typing import Any

from config import VOLUME_BOLT, VOLUME_FIRE


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("%", "").strip()
        if not text or text.upper() in {"N/A", "NONE", "NULL", "-"}:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def fmt_pct(value: Any) -> str:
    num = safe_float(value, 0.0)
    return f"{num:+.2f}%"


def fmt_krw(value: Any) -> str:
    num = safe_float(value, 0.0)
    if num <= 0:
        return "N/A"
    return f"{int(round(num)):,}원"


def fmt_foreign_net_eok(value: Any) -> str:
    amount = safe_float(value, 0.0)
    if amount == 0:
        return "N/A"
    eok = int(amount / 100_000_000)
    sign = "+" if eok > 0 else ""
    return f"{sign}{abs(eok):,}억"


def volume_emoji(volume_ratio: float) -> str:
    if volume_ratio >= VOLUME_FIRE:
        return "🔥"
    if volume_ratio >= VOLUME_BOLT:
        return "⚡"
    return ""


def position_52w_pct(price: Any, low: Any, high: Any) -> float | None:
    p = safe_float(price, 0.0)
    lo = safe_float(low, 0.0)
    hi = safe_float(high, 0.0)
    if hi <= lo or p <= 0:
        return None
    return (p - lo) / (hi - lo) * 100


def position_52w_label(price: Any, low: Any, high: Any) -> str:
    pct = position_52w_pct(price, low, high)
    if pct is None:
        return "N/A"
    return f"{pct:.0f}%"


def distance_from_high_pct(price: Any, high: Any) -> float | None:
    p = safe_float(price, 0.0)
    hi = safe_float(high, 0.0)
    if hi <= 0 or p <= 0:
        return None
    return (p - hi) / hi * 100


def indicator_change_pct(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    change = str(row.get("change", ""))
    if change.upper() == "N/A":
        return None
    try:
        return float(change.replace("%", "").replace("+", "").strip())
    except ValueError:
        return None


def normalize_phase(phase: str) -> str:
    text = (phase or "").strip()
    if "위험회피" in text or "risk" in text.lower():
        return "위험회피"
    if "강세" in text or "위험선호" in text or "bull" in text.lower():
        return "강세"
    return "중립"
