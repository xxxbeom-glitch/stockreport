"""Shared event analyzer — routes events, never creates orders."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from src.trading.competition.events.models import AnalyzedEvent, RawSignal
from src.trading.competition.events.router import route_signal

logger = logging.getLogger(__name__)

GEMINI_EVENT_MODEL = os.getenv(
    "GEMINI_EVENT_ANALYZER_MODEL",
    os.getenv("GEMINI_SUMMARY_MODEL", "gemini-2.5-flash-lite"),
)


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def analyze_with_gemini(signal: RawSignal) -> AnalyzedEvent | None:
    """Optional Gemini enrichment — falls back to None on failure."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = f"""You are a shared market event analyzer for a mock trading competition.
You do NOT create orders. Output JSON only.

Input signal:
- ticker: {signal.ticker}
- name: {signal.name}
- event_type: {signal.event_type}
- scope: {signal.scope}
- summary: {signal.summary}
- holding_teams: {signal.holding_teams}
- evidence_id: {signal.evidence.evidence_id}

Output JSON schema:
{{
  "importance": "LOW|MEDIUM|HIGH|CRITICAL",
  "direction": "POSITIVE|NEGATIVE|MIXED|UNKNOWN",
  "summary": "string",
  "affected_teams": ["A","B","C","D"],
  "requires_position_review": boolean
}}
"""
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_EVENT_MODEL)
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        parsed = _parse_json_blob(text)
        if not parsed:
            return None

        base = route_signal(signal)
        base.importance = parsed.get("importance", base.importance)  # type: ignore[assignment]
        base.direction = parsed.get("direction", base.direction)  # type: ignore[assignment]
        if parsed.get("summary"):
            base.summary = str(parsed["summary"])
        teams = parsed.get("affected_teams")
        if isinstance(teams, list) and teams:
            base.affected_teams = [str(t) for t in teams if t in ("A", "B", "C", "D")]
        if parsed.get("requires_position_review") is not None:
            base.requires_position_review = bool(parsed["requires_position_review"])
        base.analyzer_mode = "gemini"
        return base
    except Exception as exc:
        logger.warning("Gemini event analyzer failed: %s", type(exc).__name__)
        return None


def analyze_signal(
    signal: RawSignal,
    *,
    use_gemini: bool = True,
) -> AnalyzedEvent:
    """
    Analyze one signal. Always returns AnalyzedEvent with evidence_ids.
    Never creates orders.
    """
    if not signal.evidence.evidence_id:
        raise ValueError("Cannot analyze signal without evidence_id")

    if use_gemini:
        enriched = analyze_with_gemini(signal)
        if enriched:
            return enriched

    return route_signal(signal)


def analyze_signals(
    signals: list[RawSignal],
    *,
    use_gemini: bool = False,
) -> list[AnalyzedEvent]:
    """Batch analyze — gemini off by default for scan speed/cost."""
    events: list[AnalyzedEvent] = []
    for sig in signals:
        if not sig.evidence.evidence_id:
            continue
        try:
            events.append(analyze_signal(sig, use_gemini=use_gemini))
        except ValueError:
            continue
    return events
