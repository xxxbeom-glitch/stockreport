"""Shared Gemini client for pipeline agents."""

from __future__ import annotations

from typing import Any

import ai_models
import config
from utils.helpers import safe_json_parse


def _resolve_model(
    *,
    tier: ai_models.ModelTier | None = None,
    model: str | None = None,
) -> str:
    if model:
        return model
    if tier is ai_models.ModelTier.SUMMARY:
        return ai_models.model_for_tier(ai_models.ModelTier.SUMMARY)
    if tier is ai_models.ModelTier.DRAFT:
        return ai_models.model_for_tier(ai_models.ModelTier.DRAFT, engine="gemini")
    return ai_models.GEMINI_RISK_MODEL


def generate_gemini_json(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
    tier: ai_models.ModelTier = ai_models.ModelTier.VOTE,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Call Gemini and parse JSON. Default tier=VOTE (risk / judgment)."""
    if not config.GEMINI_API_KEY:
        return None
    model_name = _resolve_model(tier=tier, model=model)
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        gemini = genai.GenerativeModel(model_name)
        response = gemini.generate_content(prompt)
        if logger and getattr(response, "usage_metadata", None):
            logger.log(
                model_name,
                agent,
                input_tokens=int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0),
            )
        text = getattr(response, "text", "") or ""
        parsed = safe_json_parse(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def generate_gemini_text(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
    tier: ai_models.ModelTier = ai_models.ModelTier.SUMMARY,
    model: str | None = None,
) -> str | None:
    """Call Gemini and return plain text (default tier=SUMMARY)."""
    if not config.GEMINI_API_KEY:
        return None
    model_name = _resolve_model(tier=tier, model=model)
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        gemini = genai.GenerativeModel(model_name)
        response = gemini.generate_content(prompt)
        if logger and getattr(response, "usage_metadata", None):
            logger.log(
                model_name,
                agent,
                input_tokens=int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0),
            )
        text = (getattr(response, "text", "") or "").strip()
        return text or None
    except Exception:
        return None
