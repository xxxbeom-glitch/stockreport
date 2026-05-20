"""SectorMoodAgent — 관심 5섹터 분위기."""

from __future__ import annotations

from typing import Any

from data.kr_watchlist import SECTOR_ORDER, load_kr_watchlist_raw


def judge_sector_mood(stocks: list[dict[str, Any]], slot: str) -> dict[str, str]:
    """섹터명 → strong | neutral | weak."""
    del slot
    raw = load_kr_watchlist_raw()
    sectors = raw.get("sectors") or {}
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for row in stocks:
        by_sector.setdefault(str(row.get("sector_name", "")), []).append(row)

    mood: dict[str, str] = {}
    for key in SECTOR_ORDER:
        label = str((sectors.get(key) or {}).get("label", key))
        group = by_sector.get(label) or []
        if not group:
            mood[label] = "neutral"
            continue
        avg_vol = sum(float(r.get("volume_ratio") or 0) for r in group) / len(group)
        avg_foreign = sum(float(r.get("foreign_net_eok") or 0) for r in group) / len(group)
        if avg_vol >= 1.2 and avg_foreign > 0:
            mood[label] = "strong"
        elif avg_vol < 0.9 or avg_foreign < -30:
            mood[label] = "weak"
        else:
            mood[label] = "neutral"
    return mood
