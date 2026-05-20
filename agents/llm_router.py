"""Route LLM calls to the correct engine/model by policy tier."""

from __future__ import annotations

from typing import Any

import ai_models

from .deepseek_client import generate_deepseek_json
from .gemini_client import generate_gemini_json


def generate_vote_json(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
    prefer: str = "deepseek",
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """
    Paid-tier JSON generation for judgment/voting stages.

    prefer: "deepseek" tries DeepSeek vote first, then Gemini risk model.
    prefer: "gemini" uses Gemini risk only (e.g. risk manager).
    """
    meta: dict[str, str] = {"tier": ai_models.ModelTier.VOTE.value}

    if prefer == "gemini" or not ai_models.DEEPSEEK_API_KEY:
        parsed = generate_gemini_json(
            prompt, agent=agent, logger=logger, tier=ai_models.ModelTier.VOTE
        )
        meta["engine"] = "gemini"
        meta["model"] = ai_models.GEMINI_RISK_MODEL
        return parsed, meta

    parsed = generate_deepseek_json(
        prompt, agent=agent, logger=logger, tier=ai_models.ModelTier.VOTE
    )
    if parsed:
        meta["engine"] = "deepseek"
        meta["model"] = ai_models.DEEPSEEK_VOTE_MODEL
        return parsed, meta

    parsed = generate_gemini_json(
        prompt, agent=agent, logger=logger, tier=ai_models.ModelTier.VOTE
    )
    meta["engine"] = "gemini"
    meta["model"] = ai_models.GEMINI_RISK_MODEL
    meta["fallback"] = "deepseek_unavailable"
    return parsed, meta


def generate_draft_json(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Draft-tier JSON: DeepSeek flash first, Gemini fallback."""
    meta: dict[str, str] = {"tier": ai_models.ModelTier.DRAFT.value}

    if ai_models.DEEPSEEK_API_KEY:
        parsed = generate_deepseek_json(
            prompt, agent=agent, logger=logger, tier=ai_models.ModelTier.DRAFT
        )
        if parsed:
            meta["engine"] = "deepseek"
            meta["model"] = ai_models.DEEPSEEK_DRAFT_MODEL
            return parsed, meta

    parsed = generate_gemini_json(
        prompt, agent=agent, logger=logger, tier=ai_models.ModelTier.DRAFT
    )
    meta["engine"] = "gemini"
    meta["model"] = ai_models.model_for_tier(ai_models.ModelTier.DRAFT, engine="gemini")
    meta["fallback"] = "deepseek_unavailable"
    return parsed, meta
