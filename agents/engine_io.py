"""Typed input/output contracts for KR report AI engines (03_AI_AGENTS.md)."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class EngineMeta(TypedDict, total=False):
    engine: str
    model: str
    mode: str
    llm: dict[str, str]


# ---- Report Core Engine (Draft + data vote: DeepSeek) ----
class ReportCoreInput(TypedDict):
    market_type: str
    indices: dict[str, Any]
    market_indicators: dict[str, Any]
    sector_flow: list[dict[str, Any]]
    watchlist_data: dict[str, Any]
    supply_result: NotRequired[dict[str, Any]]
    macro_result: NotRequired[dict[str, Any]]


class ReportCoreOutput(TypedDict):
    engine: str
    model: str
    macro: dict[str, Any]
    fundamental: dict[str, Any]
    recommendations: dict[str, Any]
    draft: NotRequired[dict[str, Any]]
    meta: dict[str, Any]


# ---- Market Pulse Engine (Grok X/community) ----
class MarketPulseInput(TypedDict):
    market_type: str
    macro: dict[str, Any]
    watchlist_data: dict[str, Any]


class MarketPulseOutput(TypedDict):
    engine: str
    model: str
    supply: dict[str, Any]
    momentum: dict[str, Any]
    pulse_summary: str
    meta: dict[str, Any]


# ---- Risk Review Engine (Gemini Pro) ----
class RiskReviewInput(TypedDict):
    market_type: str
    macro: dict[str, Any]
    supply: dict[str, Any]
    momentum: dict[str, Any]
    fundamental: dict[str, Any]
    watchlist_data: dict[str, Any]


class RiskReviewOutput(TypedDict):
    engine: str
    model: str
    risk: dict[str, Any]
    meta: dict[str, Any]


# ---- Summary Compress Engine (Gemini Flash-Lite) ----
class SummaryField(TypedDict):
    key: str
    text: str
    field_name: str


class SummaryCompressInput(TypedDict):
    market_type: str
    fields: list[SummaryField]
    macro: NotRequired[dict[str, Any]]
    risk: NotRequired[dict[str, Any]]


class SummaryCompressOutput(TypedDict):
    engine: str
    model: str
    compressed: dict[str, str]
    macro: dict[str, Any]
    risk: dict[str, Any]
    meta: dict[str, Any]


# ---- KR bundle (for template / main adapters) ----
class KrEnginesBundle(TypedDict):
    market_type: str
    report_core: ReportCoreOutput
    market_pulse: MarketPulseOutput
    risk_review: RiskReviewOutput
    summary_compress: SummaryCompressOutput


class StockLabelVoteMap(TypedDict, total=False):
    """Normalized ticker -> per-stock label vote bundle."""

    pass  # runtime: dict[str, dict] from label_voting.build_pipeline_stock_labels


def build_kr_ui_comments(bundle: KrEnginesBundle) -> dict[str, str]:
    """Extract 2-line UI comment fields from engine outputs."""
    compressed = bundle["summary_compress"].get("compressed") or {}
    macro = bundle["report_core"]["macro"]
    risk = bundle["risk_review"]["risk"]
    return {
        "market_comment": compressed.get("market_phase_reason")
        or str(macro.get("market_phase_reason", "")),
        "market_one_liner": compressed.get("one_line_summary")
        or str(risk.get("one_line_summary", "")),
        "pulse_summary": bundle["market_pulse"].get("pulse_summary", ""),
    }


def legacy_pipeline_from_engines(
    *,
    report_core: ReportCoreOutput,
    market_pulse: MarketPulseOutput,
    risk_review: RiskReviewOutput,
    watchlist_data: dict[str, Any],
) -> dict[str, Any]:
    """Map engine outputs to the legacy pipeline dict consumed by main.py."""
    return {
        "macro": report_core["macro"],
        "supply": market_pulse["supply"],
        "momentum": market_pulse["momentum"],
        "fundamental": report_core["fundamental"],
        "risk": risk_review["risk"],
        "recommendations": report_core["recommendations"],
        "watchlist_data": watchlist_data,
        "engines": {
            "report_core": report_core,
            "market_pulse": market_pulse,
            "risk_review": risk_review,
        },
    }
