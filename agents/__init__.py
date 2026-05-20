"""Agent package for sequential market analysis pipeline."""

from .company_report import generate_company_report
from .engine_io import (
    KrEnginesBundle,
    build_kr_ui_comments,
    legacy_pipeline_from_engines,
)
from .label_rules import VALID_LABELS
from .label_voting import (
    AiVoteRecord,
    StockLabelVoteResult,
    ai_votes_for_template,
    build_pipeline_stock_labels,
    build_stock_label_votes,
    resolve_final_label,
)
from .fundamental import analyze_fundamental
from .kr_report_pipeline import run_kr_agent_pipeline
from .macro import analyze_macro
from .market_pulse_engine import run_market_pulse_engine
from .momentum import analyze_momentum
from .pipeline_runner import run_agent_pipeline
from .report_core_engine import run_report_core_engine
from .risk import analyze_risk
from .risk_review_engine import run_risk_review_engine
from .scorer import SCORE_THRESHOLD, calculate_score, score_breakdown
from .profiles import AGENT_PROFILES
from .recommender import get_recommendations
from .summary_compress_engine import run_summary_compress_engine
from .supply_demand import analyze_supply
from .watchlist_data import build_watchlist_data

# Legacy aliases (deprecated)
analyze_supply_demand = analyze_supply

__all__ = [
    "SCORE_THRESHOLD",
    "calculate_score",
    "score_breakdown",
    "run_agent_pipeline",
    "run_kr_agent_pipeline",
    "run_report_core_engine",
    "run_market_pulse_engine",
    "run_risk_review_engine",
    "run_summary_compress_engine",
    "build_kr_ui_comments",
    "legacy_pipeline_from_engines",
    "KrEnginesBundle",
    "build_watchlist_data",
    "analyze_macro",
    "analyze_supply",
    "analyze_supply_demand",
    "analyze_momentum",
    "analyze_fundamental",
    "analyze_risk",
    "get_recommendations",
    "generate_company_report",
    "AGENT_PROFILES",
    "VALID_LABELS",
    "AiVoteRecord",
    "StockLabelVoteResult",
    "build_stock_label_votes",
    "build_pipeline_stock_labels",
    "resolve_final_label",
    "ai_votes_for_template",
]
