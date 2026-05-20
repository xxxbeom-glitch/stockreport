"""Summary Compress Engine — 2-line UI compression (03_AI_AGENTS §5)."""

from __future__ import annotations

from typing import Any

import ai_models

from .engine_io import SummaryCompressInput, SummaryCompressOutput, SummaryField
from .summary_compress import compress_to_two_lines

ENGINE_ID = "summary_compress"


def run_summary_compress_engine(
    inp: SummaryCompressInput,
    *,
    logger: Any = None,
) -> SummaryCompressOutput:
    """Compress configured text fields to 2 lines (memo tone, no 합니다체)."""
    compressed: dict[str, str] = {}
    primary, _fallback = ai_models.summary_model_ids()

    for field in inp.get("fields") or []:
        key = str(field.get("key", ""))
        raw = str(field.get("text", "")).strip()
        if not key or not raw:
            continue
        compressed[key] = compress_to_two_lines(
            raw,
            field_name=str(field.get("field_name") or key),
            agent=f"{ENGINE_ID}_{key}",
            logger=logger,
        )

    macro = dict(inp.get("macro") or {})
    risk = dict(inp.get("risk") or {})

    if "market_phase_reason" in compressed:
        macro["market_phase_reason"] = compressed["market_phase_reason"]
        macro.setdefault("meta", {})["summary_compressed"] = True
    if "one_line_summary" in compressed:
        risk["one_line_summary"] = compressed["one_line_summary"]
        risk.setdefault("meta", {})["summary_compressed"] = True

    return {
        "engine": ENGINE_ID,
        "model": primary,
        "compressed": compressed,
        "macro": macro,
        "risk": risk,
        "meta": {
            "engine": ENGINE_ID,
            "market_type": inp.get("market_type", "KR"),
            "field_count": len(compressed),
        },
    }


def build_compress_input_from_pipeline(
    pipeline: dict[str, Any],
    *,
    market_type: str = "KR",
) -> SummaryCompressInput:
    """Build compress input from legacy or engine-augmented pipeline dict."""
    macro = pipeline.get("macro") or {}
    risk = pipeline.get("risk") or {}
    fields: list[SummaryField] = []

    reason = str(macro.get("market_phase_reason", "")).strip()
    if reason:
        fields.append(
            {"key": "market_phase_reason", "text": reason, "field_name": "market_phase_reason"}
        )
    one_line = str(risk.get("one_line_summary", "")).strip()
    if one_line:
        fields.append({"key": "one_line_summary", "text": one_line, "field_name": "one_line_summary"})

    pulse = pipeline.get("engines", {}).get("market_pulse", {})
    pulse_text = str(pulse.get("pulse_summary", "")).strip()
    if pulse_text:
        fields.append({"key": "pulse_summary", "text": pulse_text, "field_name": "market_pulse"})

    return {
        "market_type": market_type,
        "fields": fields,
        "macro": macro,
        "risk": risk,
    }
