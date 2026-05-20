"""Sequential agent pipeline orchestration."""

from __future__ import annotations

from typing import Any

from .fundamental import analyze_fundamental
from .macro import analyze_macro
from .momentum import analyze_momentum
from .recommender import get_recommendations
from .risk import analyze_risk
from .scorer import SCORE_THRESHOLD, split_watchlist_by_score
from .supply_demand import analyze_supply
from .watchlist_data import build_watchlist_data


def run_agent_pipeline(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """Run macro → supply → momentum/fundamental → risk → recommendations.

    Pre-filter: only stocks with pre_score >= 70 enter agent stages (supply onward).
    Sub-threshold stocks remain in watchlist_data for display only.
    """
    watchlist_data = build_watchlist_data(market_data)
    all_stocks = list(watchlist_data.get("stocks", []))
    agent_stocks, below_threshold = split_watchlist_by_score(all_stocks, SCORE_THRESHOLD)

    watchlist_data["stocks"] = all_stocks
    watchlist_data["agent_stocks"] = agent_stocks
    watchlist_data["below_threshold_stocks"] = below_threshold
    watchlist_data["score_threshold"] = SCORE_THRESHOLD

    agent_watchlist = {**watchlist_data, "stocks": agent_stocks}

    macro_result = analyze_macro(
        indices=market_data.get("indices") or {},
        indicators=market_data.get("market_indicators") or {},
        sector_flow=market_data.get("sector_flow") or [],
        logger=logger,
    )

    supply_result = analyze_supply(macro_result, agent_watchlist, logger=logger)
    supply_result["pre_filter"] = {
        "threshold": SCORE_THRESHOLD,
        "total_scanned": len(all_stocks),
        "passed_pre_score": len(agent_stocks),
        "below_threshold": len(below_threshold),
    }

    momentum_result = analyze_momentum(supply_result, agent_watchlist, logger=logger)
    fundamental_result = analyze_fundamental(supply_result, agent_watchlist, logger=logger)

    risk_result = analyze_risk(
        macro_result,
        supply_result,
        momentum_result,
        fundamental_result,
        agent_watchlist,
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
