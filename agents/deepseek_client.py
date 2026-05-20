"""DeepSeek API client (OpenAI-compatible) for draft / vote tiers."""

from __future__ import annotations

from typing import Any

import ai_models
from utils.helpers import safe_json_parse


def _openai_client():
    from openai import OpenAI

    return OpenAI(api_key=ai_models.DEEPSEEK_API_KEY, base_url=ai_models.DEEPSEEK_BASE_URL)


def generate_deepseek_json(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
    tier: ai_models.ModelTier = ai_models.ModelTier.VOTE,
) -> dict[str, Any] | None:
    """Call DeepSeek chat completions and parse JSON from the response."""
    if not ai_models.DEEPSEEK_API_KEY:
        return None
    model_name = ai_models.model_for_tier(tier, engine="deepseek")
    try:
        client = _openai_client()
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        if logger and getattr(response, "usage", None):
            usage = response.usage
            logger.log(
                model_name,
                agent,
                input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            )
        text = (response.choices[0].message.content or "").strip()
        parsed = safe_json_parse(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def generate_deepseek_text(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
    tier: ai_models.ModelTier = ai_models.ModelTier.DRAFT,
    max_tokens: int = 512,
) -> str | None:
    """Call DeepSeek and return plain text."""
    if not ai_models.DEEPSEEK_API_KEY:
        return None
    model_name = ai_models.model_for_tier(tier, engine="deepseek")
    try:
        client = _openai_client()
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        if logger and getattr(response, "usage", None):
            usage = response.usage
            logger.log(
                model_name,
                agent,
                input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            )
        return (response.choices[0].message.content or "").strip() or None
    except Exception:
        return None
