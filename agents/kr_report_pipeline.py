"""KR report orchestration across 4 AI engines (03_AI_AGENTS.md)."""

from __future__ import annotations

from typing import Any

import ai_models

from .engine_io import (
    KrEnginesBundle,
    MarketPulseInput,
    ReportCoreInput,
    RiskReviewInput,
    build_kr_ui_comments,
    legacy_pipeline_from_engines,
)
from .market_pulse_engine import run_market_pulse_engine
from .label_voting import build_pipeline_stock_labels
from .recommender import get_recommendations
from .report_core_engine import run_report_core_engine
from .risk_review_engine import run_risk_review_engine
from .scorer import SCORE_THRESHOLD, split_watchlist_by_score
from .summary_compress_engine import (
    build_compress_input_from_pipeline,
    run_summary_compress_engine,
)
from .watchlist_data import build_watchlist_data


def run_kr_agent_pipeline(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """
    KR agent flow:
      1. Report Core (macro draft + rules)
      2. Market Pulse (Grok supply/momentum)
      3. Report Core phase 2 (fundamental vote + recommendations)
      4. Risk Review (Gemini)
      5. Summary Compress (Flash-Lite)
    Returns legacy pipeline dict + ``engines`` + ``kr_ui``.
    """
    watchlist_data = build_watchlist_data(market_data)
    all_stocks = list(watchlist_data.get("stocks", []))
    agent_stocks, below_threshold = split_watchlist_by_score(all_stocks, SCORE_THRESHOLD)

    watchlist_data["stocks"] = all_stocks
    watchlist_data["agent_stocks"] = agent_stocks
    watchlist_data["below_threshold_stocks"] = below_threshold
    watchlist_data["score_threshold"] = SCORE_THRESHOLD

    agent_watchlist = {**watchlist_data, "stocks": agent_stocks}
    base_inp = {
        "market_type": "KR",
        "indices": market_data.get("indices") or {},
        "market_indicators": market_data.get("market_indicators") or {},
        "sector_flow": market_data.get("sector_flow") or [],
        "watchlist_data": agent_watchlist,
    }

    report_core_1: ReportCoreInput = {**base_inp}  # type: ignore[misc]
    core_phase1 = run_report_core_engine(report_core_1, logger=logger, include_recommendations=False)

    pulse_inp: MarketPulseInput = {
        "market_type": "KR",
        "macro": core_phase1["macro"],
        "watchlist_data": agent_watchlist,
    }
    market_pulse = run_market_pulse_engine(pulse_inp, logger=logger)
    market_pulse["supply"]["pre_filter"] = {
        "threshold": SCORE_THRESHOLD,
        "total_scanned": len(all_stocks),
        "passed_pre_score": len(agent_stocks),
        "below_threshold": len(below_threshold),
    }

    report_core_2: ReportCoreInput = {
        **base_inp,
        "supply_result": market_pulse["supply"],
        "macro_result": core_phase1["macro"],
    }  # type: ignore[misc]
    core_phase2 = run_report_core_engine(
        report_core_2,
        logger=logger,
        include_recommendations=False,
    )
    if core_phase1.get("draft"):
        core_phase2["draft"] = core_phase1["draft"]

    risk_inp: RiskReviewInput = {
        "market_type": "KR",
        "macro": core_phase2["macro"],
        "supply": market_pulse["supply"],
        "momentum": market_pulse["momentum"],
        "fundamental": core_phase2["fundamental"],
        "watchlist_data": agent_watchlist,
    }
    risk_review = run_risk_review_engine(risk_inp, logger=logger)

    core_phase2["recommendations"] = get_recommendations(
        core_phase2["macro"],
        market_pulse["supply"],
        market_pulse["momentum"],
        core_phase2["fundamental"],
        risk_review["risk"],
        watchlist_data,
        logger=logger,
    )

    legacy = legacy_pipeline_from_engines(
        report_core=core_phase2,
        market_pulse=market_pulse,
        risk_review=risk_review,
        watchlist_data=watchlist_data,
    )

    compress_inp = build_compress_input_from_pipeline(legacy, market_type="KR")
    summary_compress = run_summary_compress_engine(compress_inp, logger=logger)
    legacy["macro"] = summary_compress["macro"]
    legacy["risk"] = summary_compress["risk"]

    bundle: KrEnginesBundle = {
        "market_type": "KR",
        "report_core": core_phase2,
        "market_pulse": market_pulse,
        "risk_review": risk_review,
        "summary_compress": summary_compress,
    }
    legacy["engines"] = {
        **legacy.get("engines", {}),
        "summary_compress": summary_compress,
        "bundle": bundle,
    }
    legacy["kr_ui"] = build_kr_ui_comments(bundle)
    build_pipeline_stock_labels(legacy)
    legacy.setdefault("meta", {})["ai_models"] = ai_models.policy_snapshot()
    legacy["meta"]["pipeline"] = "kr_4_engines"
    return legacy
