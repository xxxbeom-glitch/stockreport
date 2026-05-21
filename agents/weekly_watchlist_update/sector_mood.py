"""주간 섹터 분위기 (관심 25종목 메트릭 기반)."""

from __future__ import annotations

from typing import Any

from data.kr_watchlist import watchlist_sector_labels


def judge_weekly_sector_mood(metrics: list[dict[str, Any]]) -> dict[str, str]:
    """섹터명 → strong | neutral | weak."""
    labels = watchlist_sector_labels()
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for row in metrics:
        by_sector.setdefault(str(row.get("sector", "")), []).append(row)

    mood: dict[str, str] = {}
    for label in labels:
        group = by_sector.get(label) or []
        if not group:
            mood[label] = "neutral"
            continue
        usable = [
            r
            for r in group
            if str(r.get("data_status") or "") not in ("missing_ohlcv", "")
            and (r.get("data_status") or r.get("data_quality"))
        ]
        if not usable:
            mood[label] = "neutral"
            continue
        avg_ret = sum(float(r.get("return_5d") or 0) for r in usable) / len(usable)
        avg_tv = sum(float(r.get("tv_growth_5d_vs_10d") or 0) for r in usable) / len(usable)
        rs_vals = [
            float(r["sector_relative_strength"])
            for r in usable
            if r.get("sector_relative_strength") is not None
        ]
        avg_rs = sum(rs_vals) / len(rs_vals) if rs_vals else 50.0
        if avg_ret >= 2.0 and avg_tv >= 0.05 and avg_rs >= 55:
            mood[label] = "strong"
        elif avg_ret < -2.0 or avg_tv < -0.1 or avg_rs < 35:
            mood[label] = "weak"
        else:
            mood[label] = "neutral"
    return mood
