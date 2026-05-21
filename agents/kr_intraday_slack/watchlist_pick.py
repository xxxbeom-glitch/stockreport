"""WatchlistPickAgent — 단타용 장중 1차 후보 선별 (진입 가능성 있는 종목만)."""

from __future__ import annotations

from typing import Any

from .entry_price import is_chasing_price

# 장중 고점 대비 — 이보다 가까우면 추격 위험으로 제외
_CHASE_EXCLUDE_RATIO = 0.985
_MIN_SCORE_DEFAULT = 3.0
_MIN_SCORE_WEAK_SECTOR = 4.5


def _score_row(
    row: dict[str, Any],
    mood: str,
) -> float | None:
    if not row.get("data_complete"):
        return None
    vol = float(row.get("volume_ratio") or 0)
    foreign = float(row.get("foreign_net_eok") or 0)
    inst = float(row.get("inst_net_eok") or 0)
    current = float(row.get("current_price") or 0)
    day_high = float(row.get("day_high") or current)
    if current <= 0 or day_high <= 0:
        return None
    if is_chasing_price(row) or current / day_high >= _CHASE_EXCLUDE_RATIO:
        return None

    vol_floor = 0.85 if mood == "weak" else 0.75
    if vol < vol_floor:
        return None
    if mood == "weak" and foreign < -20:
        return None

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
    elif mood == "weak":
        score -= 0.5
    if float(row.get("pullback_from_high_pct") or 0) >= 0.03:
        score += 0.5
    min_score = _MIN_SCORE_WEAK_SECTOR if mood == "weak" else _MIN_SCORE_DEFAULT
    if score < min_score:
        return None
    return score


def pick_sector_candidates(
    stocks: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    slot: str,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """섹터 단위 1차 후보 (병렬 스캔 후 merge에서 전역 상한 적용)."""
    del slot
    sector = str(stocks[0].get("sector_name", "")) if stocks else ""
    mood = sector_mood.get(sector, "neutral")
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in stocks:
        score = _score_row(row, mood)
        if score is not None:
            scored.append((score, {**row, "_pick_score": score}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def pick_watchlist_candidates(
    stocks: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    slot: str,
) -> list[dict[str, Any]]:
    """전체 종목 1차 후보 (레거시·단일 패스용, 최대 7)."""
    del slot
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in stocks:
        sector = str(row.get("sector_name", ""))
        mood = sector_mood.get(sector, "neutral")
        score = _score_row(row, mood)
        if score is not None:
            scored.append((score, {**row, "_pick_score": score}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:7]]
