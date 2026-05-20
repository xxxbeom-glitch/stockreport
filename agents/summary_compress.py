"""2-line UI summary compression (free/low-cost Gemini tier)."""

from __future__ import annotations

from typing import Any

import ai_models
import config
from utils.ui_comment import format_ui_comment


def _compress_with_gemini(
    text: str,
    *,
    field_name: str,
    agent: str,
    logger: Any = None,
    model_name: str,
) -> str | None:
    if not config.GEMINI_API_KEY or not text.strip():
        return None
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name)
        prompt = f"""
아래 주식 리포트 문장을 **정확히 2줄**로만 압축하세요.
- 사실·수치는 원문에 있는 것만 사용 (추측·신규 수치 금지)
- 초보 투자자 톤, 인사말·서론 없음
- 각 줄은 한 문장, 줄바꿈 1회만
- 필드: {field_name}

[원문]
{text.strip()[:4000]}
"""
        response = model.generate_content(prompt)
        if logger and getattr(response, "usage_metadata", None):
            logger.log(
                model_name,
                agent,
                input_tokens=int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0),
            )
        out = (getattr(response, "text", "") or "").strip()
        return out if out else None
    except Exception:
        return None


def compress_to_two_lines(
    text: str,
    *,
    field_name: str = "summary",
    agent: str = "summary_compress",
    logger: Any = None,
) -> str:
    """Compress long text to 2 lines; returns original if compression unavailable."""
    raw = (text or "").strip()
    if not raw:
        return raw
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) <= 2 and len(raw) <= 280:
        return raw

    primary, fallback = ai_models.summary_model_ids()
    for model_name in (primary, fallback):
        compressed = _compress_with_gemini(
            raw,
            field_name=field_name,
            agent=agent,
            logger=logger,
            model_name=model_name,
        )
        if compressed:
            return format_ui_comment(compressed)
    return format_ui_comment(raw)


def compress_pipeline_summaries(pipeline: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """Apply 2-line compression via Summary Compress Engine."""
    from .summary_compress_engine import (
        build_compress_input_from_pipeline,
        run_summary_compress_engine,
    )

    if (pipeline.get("engines") or {}).get("summary_compress"):
        return pipeline

    compress_inp = build_compress_input_from_pipeline(pipeline, market_type="KR")
    result = run_summary_compress_engine(compress_inp, logger=logger)
    pipeline["macro"] = result["macro"]
    pipeline["risk"] = result["risk"]
    pipeline.setdefault("engines", {})["summary_compress"] = result
    pipeline.setdefault("meta", {})["ai_models"] = ai_models.policy_snapshot()
    return pipeline
