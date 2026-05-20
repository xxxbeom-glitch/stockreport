"""Central AI model policy for KR/US stock reports.

See docs/ko_stock_report_cursor_md/02_AI_MODEL_POLICY.md
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Final

from dotenv import load_dotenv

load_dotenv()


class ModelTier(str, Enum):
    """Cost/role tier — maps to env-backed model IDs."""

    DRAFT = "draft"  # data summary, report draft (paid/low)
    VOTE = "vote"  # judgment, voting, inference (paid/top)
    SUMMARY = "summary"  # 2-line UI compression (free/low)


# ---- API keys ----
DEEPSEEK_API_KEY: Final[str] = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: Final[str] = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# ---- Model IDs (.env overrides per 02_AI_MODEL_POLICY.md) ----
DEEPSEEK_DRAFT_MODEL: Final[str] = os.getenv("DEEPSEEK_DRAFT_MODEL", "deepseek-v4-flash")
DEEPSEEK_VOTE_MODEL: Final[str] = os.getenv("DEEPSEEK_VOTE_MODEL", "deepseek-v4-pro")

GROK_VOTE_MODEL: Final[str] = os.getenv("GROK_VOTE_MODEL", os.getenv("GROK_MODEL", "grok-4.3"))

GEMINI_RISK_MODEL: Final[str] = os.getenv(
    "GEMINI_RISK_MODEL",
    os.getenv("GEMINI_PRO_MODEL", "gemini-3.1-pro-preview"),
)
GEMINI_SUMMARY_MODEL: Final[str] = os.getenv(
    "GEMINI_SUMMARY_MODEL",
    "gemini-3.1-flash-lite-preview",
)
GEMINI_SUMMARY_FALLBACK_MODEL: Final[str] = os.getenv(
    "GEMINI_SUMMARY_FALLBACK_MODEL",
    os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash-lite"),
)

# ---- KR report engines (03_AI_AGENTS.md) ----
KR_ENGINE_IDS: Final[tuple[str, ...]] = (
    "report_core",
    "market_pulse",
    "risk_review",
    "summary_compress",
)

KR_ENGINE_MODEL: Final[dict[str, str]] = {
    "report_core": DEEPSEEK_DRAFT_MODEL,
    "market_pulse": GROK_VOTE_MODEL,
    "risk_review": GEMINI_RISK_MODEL,
    "summary_compress": GEMINI_SUMMARY_MODEL,
}

# ---- KR report: which tier each pipeline stage uses ----
KR_REPORT_STAGE_TIER: Final[dict[str, ModelTier]] = {
    "report_core": ModelTier.DRAFT,
    "report_core_vote": ModelTier.VOTE,
    "market_pulse": ModelTier.VOTE,
    "risk_review": ModelTier.VOTE,
    "summary_compress": ModelTier.SUMMARY,
    "company_report": ModelTier.DRAFT,
    "macro_polish": ModelTier.VOTE,
    "supply_x_vote": ModelTier.VOTE,
    "momentum_x_vote": ModelTier.VOTE,
    "fundamental_vote": ModelTier.VOTE,
    "risk_vote": ModelTier.VOTE,
    "recommender_polish": ModelTier.VOTE,
    "ui_summary": ModelTier.SUMMARY,
}

# ---- Engine preference per tier (first available wins for vote/draft) ----
_TIER_MODEL: Final[dict[ModelTier, dict[str, str]]] = {
    ModelTier.DRAFT: {
        "deepseek": DEEPSEEK_DRAFT_MODEL,
        "gemini": GEMINI_SUMMARY_FALLBACK_MODEL,
    },
    ModelTier.VOTE: {
        "deepseek": DEEPSEEK_VOTE_MODEL,
        "grok": GROK_VOTE_MODEL,
        "gemini": GEMINI_RISK_MODEL,
    },
    ModelTier.SUMMARY: {
        "gemini": GEMINI_SUMMARY_MODEL,
        "gemini_fallback": GEMINI_SUMMARY_FALLBACK_MODEL,
    },
}


def tier_for_stage(stage: str, *, market: str = "KR") -> ModelTier:
    """Return model tier for a named pipeline stage (KR default)."""
    del market  # US shares same tiers for now
    return KR_REPORT_STAGE_TIER.get(stage, ModelTier.VOTE)


def model_for_tier(tier: ModelTier, *, engine: str | None = None) -> str:
    """Resolve concrete model ID for a tier (optional engine: deepseek|grok|gemini)."""
    mapping = _TIER_MODEL[tier]
    if engine:
        return mapping[engine]
    if tier is ModelTier.SUMMARY:
        return mapping["gemini"]
    if tier is ModelTier.DRAFT:
        return mapping["deepseek"]
    return mapping.get("gemini", GEMINI_RISK_MODEL)


def summary_model_ids() -> tuple[str, str]:
    """Primary and fallback Gemini models for 2-line compression."""
    return GEMINI_SUMMARY_MODEL, GEMINI_SUMMARY_FALLBACK_MODEL


def policy_snapshot() -> dict[str, str | bool]:
    """Export active model policy for logging / report meta."""
    return {
        "deepseek_enabled": bool(DEEPSEEK_API_KEY),
        "deepseek_draft": DEEPSEEK_DRAFT_MODEL,
        "deepseek_vote": DEEPSEEK_VOTE_MODEL,
        "grok_vote": GROK_VOTE_MODEL,
        "gemini_risk": GEMINI_RISK_MODEL,
        "gemini_summary": GEMINI_SUMMARY_MODEL,
        "gemini_summary_fallback": GEMINI_SUMMARY_FALLBACK_MODEL,
    }


# Backward-compatible aliases (legacy config.py names)
GEMINI_PRO_MODEL: Final[str] = GEMINI_RISK_MODEL
GEMINI_FLASH_MODEL: Final[str] = GEMINI_SUMMARY_FALLBACK_MODEL
GROK_MODEL: Final[str] = GROK_VOTE_MODEL
