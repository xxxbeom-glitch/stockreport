"""Sequential agent pipeline orchestration."""

from __future__ import annotations

from typing import Any

from .fundamental import analyze_fundamental
from .macro import analyze_macro
from .momentum import analyze_momentum
from .recommender import get_recommendations
from .risk import analyze_risk
from .supply_demand import analyze_supply
from .watchlist_data import build_watchlist_data


def run_agent_pipeline(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """Run macro → supply → momentum/fundamental → risk → recommendations."""
    watchlist_data = build_watchlist_data(market_data)

    macro_result = analyze_macro(
        indices=market_data.get("indices") or {},
        indicators=market_data.get("market_indicators") or {},
        sector_flow=market_data.get("sector_flow") or [],
        logger=logger,
    )

    supply_result = analyze_supply(macro_result, watchlist_data, logger=logger)

    momentum_result = analyze_momentum(supply_result, watchlist_data, logger=logger)
    fundamental_result = analyze_fundamental(supply_result, watchlist_data, logger=logger)

    risk_result = analyze_risk(
        macro_result,
        supply_result,
        momentum_result,
        fundamental_result,
        watchlist_data,
        logger=logger,
    )

    recommendations = get_recommendations(
        macro_result,
        supply_result,
        momentum_result,
        fundamental_result,
        risk_result,
        watchlist_data,
        logger=logger,
    )

    return {
        "macro": macro_result,
        "supply": supply_result,
        "momentum": momentum_result,
        "fundamental": fundamental_result,
        "risk": risk_result,
        "recommendations": recommendations,
        "watchlist_data": watchlist_data,
    }
