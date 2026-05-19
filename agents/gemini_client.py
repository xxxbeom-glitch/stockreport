"""Shared Gemini client for pipeline agents."""

from __future__ import annotations

from typing import Any

import config
from utils.helpers import safe_json_parse


def generate_gemini_json(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
) -> dict[str, Any] | None:
    """Call Gemini Pro model and parse JSON from the response text."""
    if not config.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_PRO_MODEL)
        response = model.generate_content(prompt)
        if logger and getattr(response, "usage_metadata", None):
            logger.log(
                config.GEMINI_PRO_MODEL,
                agent,
                input_tokens=int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0),
            )
        text = getattr(response, "text", "") or ""
        parsed = safe_json_parse(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None
