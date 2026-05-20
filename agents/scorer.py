"""Rule-based pre-filter scoring before LLM agent pipeline."""

from __future__ import annotations

from typing import Any

from config import VOLUME_BOLT, VOLUME_FIRE

from .common import position_52w_pct, safe_float

SCORE_THRESHOLD: int = 70


def calculate_score(stock_data: dict[str, Any]) -> int:
    """Return 0–100 pre-filter score (supply 40 + momentum 30 + valuation 30)."""
    breakdown = score_breakdown(stock_data)
    return int(breakdown["total"])


def score_breakdown(stock_data: dict[str, Any]) -> dict[str, Any]:
    """Return score components for logging and watchlist display."""
    supply = _supply_points(stock_data)
    momentum = _momentum_points(stock_data)
    valuation = _valuation_points(stock_data)
    total = min(100, supply + momentum + valuation)
    return {
        "supply": supply,
        "momentum": momentum,
        "valuation": valuation,
        "total": total,
    }


def _supply_points(stock: dict[str, Any]) -> int:
    score = 0
    foreign = stock.get("foreign_net")
    if foreign is not None and safe_float(foreign, 0.0) > 0:
        score += 20

    strength = stock.get("conclusion_strength")
    if strength is not None and safe_float(strength, 0.0) >= 100:
        score += 10

    streak = stock.get("foreign_buy_days") or stock.get("foreign_net_streak")
    if streak is not None and int(safe_float(streak, 0)) >= 3:
        score += 10
    elif stock.get("foreign_3d_buy") is True:
        score += 10

    return min(40, score)


def _momentum_points(stock: dict[str, Any]) -> int:
    score = 0
    vol = safe_float(stock.get("volume_ratio"), 0.0)
    if vol >= VOLUME_FIRE:
        score += 15
    elif vol >= VOLUME_BOLT:
        score += 10

    pos = position_52w_pct(stock.get("price"), stock.get("low_52"), stock.get("high_52"))
    if pos is not None:
        if pos >= 90:
            score += 15
        elif pos <= 30:
            score += 10

    return min(30, score)


def _valuation_points(stock: dict[str, Any]) -> int:
    pbr = stock.get("pbr")
    if pbr is None:
        return 0
    pbr_v = safe_float(pbr, 0.0)
    if pbr_v <= 0:
        return 0
    if pbr_v <= 1:
        return 30
    if pbr_v <= 2:
        return 20
    if pbr_v <= 3:
        return 10
    return 0


def split_watchlist_by_score(
    stocks: list[dict[str, Any]], threshold: int = SCORE_THRESHOLD
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Annotate each stock with pre_score; return (agent_targets, watchlist_only)."""
    agent_targets: list[dict[str, Any]] = []
    watchlist_only: list[dict[str, Any]] = []

    for stock in stocks:
        bd = score_breakdown(stock)
        stock["pre_score"] = bd["total"]
        stock["score_breakdown"] = bd
        if bd["total"] >= threshold:
            agent_targets.append(stock)
        else:
            watchlist_only.append(stock)

    agent_targets.sort(key=lambda s: s.get("pre_score", 0), reverse=True)
    return agent_targets, watchlist_only
