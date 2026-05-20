"""Market Pulse Engine — X/community pulse via Grok (03_AI_AGENTS §3)."""

from __future__ import annotations

from typing import Any

import ai_models

from .engine_io import MarketPulseInput, MarketPulseOutput
from .momentum import analyze_momentum
from .supply_demand import analyze_supply

ENGINE_ID = "market_pulse"


def run_market_pulse_engine(inp: MarketPulseInput, *, logger: Any = None) -> MarketPulseOutput:
    """Run supply (X 수급) + momentum (X 모멘텀) and attach pulse summary."""
    wl = inp["watchlist_data"]
    macro = inp["macro"]

    supply = analyze_supply(macro, wl, logger=logger)
    momentum = analyze_momentum(supply, wl, logger=logger)

    pulse_parts: list[str] = []
    if supply.get("summary"):
        pulse_parts.append(str(supply["summary"]))
    if supply.get("x_supply_buzz"):
        pulse_parts.append(str(supply["x_supply_buzz"]))
    if momentum.get("summary"):
        pulse_parts.append(str(momentum["summary"]))
    pulse_summary = " ".join(pulse_parts).strip() or "X/커뮤니티 데이터 불충분"

    return {
        "engine": ENGINE_ID,
        "model": ai_models.GROK_VOTE_MODEL,
        "supply": supply,
        "momentum": momentum,
        "pulse_summary": pulse_summary[:500],
        "meta": {
            "engine": ENGINE_ID,
            "market_type": inp.get("market_type", "KR"),
            "supply_mode": (supply.get("meta") or {}).get("mode"),
            "momentum_mode": (momentum.get("meta") or {}).get("mode"),
        },
    }
