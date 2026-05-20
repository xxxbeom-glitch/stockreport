"""Risk Review Engine — conservative label review via Gemini Pro (03_AI_AGENTS §4)."""

from __future__ import annotations

from typing import Any

import ai_models

from .engine_io import RiskReviewInput, RiskReviewOutput
from .risk import analyze_risk

ENGINE_ID = "risk_review"


def run_risk_review_engine(inp: RiskReviewInput, *, logger: Any = None) -> RiskReviewOutput:
    """Run risk manager stage (rules + Gemini Pro review)."""
    risk = analyze_risk(
        inp["macro"],
        inp["supply"],
        inp["momentum"],
        inp["fundamental"],
        inp["watchlist_data"],
        logger=logger,
    )
    return {
        "engine": ENGINE_ID,
        "model": ai_models.GEMINI_RISK_MODEL,
        "risk": risk,
        "meta": {
            "engine": ENGINE_ID,
            "market_type": inp.get("market_type", "KR"),
            "mode": (risk.get("meta") or {}).get("mode"),
        },
    }
