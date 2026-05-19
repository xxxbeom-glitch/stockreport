"""Agent package for sequential market analysis pipeline."""

from .company_report import generate_company_report
from .fundamental import analyze_fundamental
from .macro import analyze_macro
from .momentum import analyze_momentum
from .pipeline_runner import run_agent_pipeline
from .profiles import AGENT_PROFILES
from .recommender import get_recommendations
from .risk import analyze_risk
from .supply_demand import analyze_supply
from .watchlist_data import build_watchlist_data

# Legacy aliases (deprecated)
analyze_supply_demand = analyze_supply

__all__ = [
    "run_agent_pipeline",
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
]
