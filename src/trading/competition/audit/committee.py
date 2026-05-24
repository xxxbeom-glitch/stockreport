"""Audit committee — optional AI evaluation (does not override code auditor)."""

from __future__ import annotations

import json
from typing import Any


def run_audit_committee(
    *,
    replay_run_id: str,
    snapshot: dict[str, Any],
    decisions: list[dict[str, Any]],
    team_results: dict[str, Any],
    force_mock: bool = False,
) -> dict[str, Any]:
    """
    Lead + challenger evaluation. Code leakage FAIL is passed through unchanged.
  """
    code_summary = {
        "replay_run_id": replay_run_id,
        "snapshot_id": snapshot.get("snapshot_id"),
        "decisions": [
            {
                "team_id": d.get("team_id"),
                "action": d.get("action"),
                "leakage_audit": d.get("leakage_audit"),
                "reason_label": d.get("reason_label"),
            }
            for d in decisions
        ],
        "team_results": team_results,
    }

    lead = _call_audit_model("AUDIT_LEAD", code_summary, force_mock=force_mock)
    challenger = _call_audit_model("AUDIT_CHALLENGER", {**code_summary, "lead": lead}, force_mock=force_mock)

    return {
        "ok": True,
        "replay_run_id": replay_run_id,
        "lead_evaluation": lead,
        "challenger_review": challenger,
        "note": "AI does not override code_auditor FAIL; leakage status quoted from decisions.",
    }


def _call_audit_model(role: str, payload: dict[str, Any], *, force_mock: bool) -> dict[str, Any]:
    if force_mock:
        return {
            "role": role,
            "verdict": "mock_skipped",
            "summary": "Audit AI skipped in mock mode.",
        }

    import os

    from src.trading.competition.teams.config import provider_available, resolve_model

    model_role = "D_VALIDATOR" if role == "AUDIT_CHALLENGER" else "C_MAIN"
    provider, model = resolve_model(model_role, force_mock=False)
    if provider == "mock" or not provider_available(provider):
        return {
            "role": role,
            "verdict": "unavailable",
            "summary": f"Model unavailable for {model_role}",
        }

    prompt = (
        "You are an audit committee member. Do NOT re-judge future-data leakage; "
        "quote code auditor leakage_audit fields only. Return JSON with verdict, summary, findings[].\n"
        f"PAYLOAD:\n{json.dumps(payload, ensure_ascii=False)[:12000]}"
    )
    try:
        if provider == "gemini":
            from agents.gemini_client import generate_gemini_json

            raw = generate_gemini_json(prompt, agent="competition_audit", model=model)
        else:
            from agents.deepseek_client import generate_deepseek_json

            raw = generate_deepseek_json(prompt, agent="competition_audit")
        return raw if isinstance(raw, dict) else {"role": role, "verdict": "parse_failed", "raw": str(raw)[:500]}
    except Exception as exc:
        return {"role": role, "verdict": "error", "error": str(exc)}
