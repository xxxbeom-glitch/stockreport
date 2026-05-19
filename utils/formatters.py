"""Display formatters for report payloads."""

from __future__ import annotations

from typing import Any


def foreign_net_eok(value: Any) -> str:
    """Convert KRW amount to 억원 string."""
    if value is None:
        return "N/A"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "N/A"
    eok = int(amount / 100_000_000)
    sign = "-" if eok < 0 else ""
    eok_abs = abs(eok)
    if eok_abs >= 100:
        return f"{sign}{eok_abs:,}억원"
    return f"{sign}{eok_abs:.1f}억원"
