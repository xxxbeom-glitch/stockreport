"""WatchlistPickAgent — 25개 중 1차 후보 선별."""

from __future__ import annotations

from typing import Any


def pick_watchlist_candidates(
    stocks: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    slot: str,
) -> list[dict[str, Any]]:
    """03_scan_logic.md 선별 기준 (규칙 기반 더미)."""
    del slot
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in stocks:
        if not row.get("data_complete"):
            continue
        sector = str(row.get("sector_name", ""))
        mood = sector_mood.get(sector, "neutral")
        vol = float(row.get("volume_ratio") or 0)
        foreign = float(row.get("foreign_net_eok") or 0)
        inst = float(row.get("inst_net_eok") or 0)
        current = float(row.get("current_price") or 0)
        day_high = float(row.get("day_high") or current)
        if current <= 0 or day_high <= 0:
            continue
        near_high = current / day_high >= 0.985
        if near_high:
            continue

        score = 0.0
        if vol >= 1.0:
            score += 2.0
        if vol >= 1.3:
            score += 1.0
        if foreign > 0:
            score += 1.5
        if inst > 0:
            score += 0.5
        if mood == "strong":
            score += 2.0
        elif mood == "neutral":
            score += 0.5
        if float(row.get("pullback_from_high_pct") or 0) >= 0.03:
            score += 0.5

        if score < 3.0:
            continue
        scored.append((score, {**row, "_pick_score": score}))

    scored.sort(key=lambda x: x[0], reverse=True)
    # 규칙 1차 후보 3~7개 → LLM 배치 판단용
    return [r for _, r in scored[:7]]
