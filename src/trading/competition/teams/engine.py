"""Team decision engine — main + partner/validator."""

from __future__ import annotations

import json
import uuid
from typing import Any

from src.trading.competition.decision.models import DecisionTrigger
from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.journal import append_ai_usage_log, append_decision
from src.trading.competition.teams.config import provider_available, resolve_model
from src.trading.competition.teams.input_builder import build_team_input
from src.trading.competition.teams.mock_provider import (
    mock_main_decision,
    mock_partner_note,
    mock_validator_review,
)
from src.trading.competition.teams.schemas import normalize_decision, validate_decision, validate_partner_review

FAST_TEAMS = frozenset({"A", "B"})
VERIFY_TEAMS = frozenset({"C", "D"})


def _role_main(team_id: str) -> str:
    return f"{team_id}_MAIN"


def _role_partner(team_id: str) -> str:
    return f"{team_id}_PARTNER" if team_id in FAST_TEAMS else f"{team_id}_VALIDATOR"


def _call_llm_json(provider: str, model: str, prompt: str, *, agent: str) -> dict[str, Any] | None:
    if provider == "mock":
        return None
    try:
        if provider == "gemini":
            from agents.gemini_client import generate_gemini_json

            return generate_gemini_json(prompt, agent=agent, model=model)
        if provider == "deepseek":
            from agents.deepseek_client import generate_deepseek_json

            return generate_deepseek_json(prompt, agent=agent)
    except Exception:
        return None
    return None


def _build_prompt(team_input: dict[str, Any]) -> str:
    import os

    replay_note = ""
    if (os.getenv("COMPETITION_EXECUTION_MODE") or "").startswith("replay"):
        replay_note = (
            "REPLAY MODE: Use ONLY the JSON INPUT below. "
            "No web search, no external API calls, no prices or news after decision_at. "
            "If data is insufficient, return HOLD or WAIT.\n"
        )
    return (
        f"{replay_note}"
        "You are an AI trading team. Return ONLY valid JSON matching the decision schema.\n"
        "Required fields for BUY: action, ticker, quantity, allocation_krw, order_type, "
        "target_price, reason_label, reason_detail, review_conditions (array), evidence_ids (array).\n"
        "Rules: HOLD/WAIT if uncertain; BUY requires evidence_ids from INPUT, target_price, review_conditions.\n"
        "reason_label must be a short Korean label (required).\n"
        f"INPUT:\n{json.dumps(team_input, ensure_ascii=False)}"
    )


def run_main_decision(
    trigger: DecisionTrigger,
    *,
    force_mock: bool = False,
) -> dict[str, Any]:
    team_id = trigger.team_id
    team_input = build_team_input(trigger)
    role = _role_main(team_id)
    provider, model = resolve_model(role, force_mock=force_mock)

    raw: dict[str, Any] | None = None
    used_mock = False
    if provider == "mock" or not provider_available(provider):
        raw = mock_main_decision(team_input, role=role)
        used_mock = True
    else:
        raw = _call_llm_json(provider, model, _build_prompt(team_input), agent=f"competition_{team_id}")
        if not raw:
            raw = mock_main_decision(team_input, role=role)
            used_mock = True

    raw.setdefault("trigger_type", trigger.trigger_type)
    raw.setdefault("trigger_event_ids", trigger.event_ids)
    raw.setdefault("session_id", trigger.session_id)
    raw.setdefault("team_id", team_id)
    raw.setdefault("decision_id", f"dec_{uuid.uuid4().hex[:12]}")
    raw.setdefault("created_at", now_kst_iso())

    normalized = normalize_decision(raw)
    ok, errors = validate_decision(normalized)
    if not ok:
        normalized = normalize_decision(mock_main_decision(team_input, role=role))
        normalized["reason_detail"] = f"schema_fallback: {errors}"
        used_mock = True

    append_ai_usage_log(
        {
            "log_id": f"log_{uuid.uuid4().hex[:12]}",
            "team_id": team_id,
            "role": role,
            "provider": "mock" if used_mock else provider,
            "model": model,
            "trigger_id": trigger.trigger_id,
            "created_at": now_kst_iso(),
        }
    )
    append_decision(normalized)
    return normalized


def run_partner_or_validator(
    decision: dict[str, Any],
    *,
    force_mock: bool = False,
) -> dict[str, Any] | None:
    team_id = str(decision.get("team_id") or "")
    if team_id in FAST_TEAMS:
        if decision.get("action") not in ("BUY", "ADD_BUY", "PARTIAL_SELL", "FULL_SELL"):
            return None
        role = _role_partner(team_id)
        provider, model = resolve_model(role, force_mock=force_mock)
        note = mock_partner_note(decision, role=role)
        if note:
            note["provider"] = "mock" if provider == "mock" else provider
        return note

    if team_id not in VERIFY_TEAMS:
        return None

    role = _role_partner(team_id)
    provider, model = resolve_model(role, force_mock=force_mock)
    review: dict[str, Any]
    used_mock = provider == "mock" or not provider_available(provider)
    if used_mock:
        review = mock_validator_review(decision, role=role)
    else:
        prompt = (
            "Validate the proposed decision. Return JSON with result APPROVE|REDUCE|HOLD|REJECT.\n"
            f"DECISION:\n{json.dumps(decision, ensure_ascii=False)}"
        )
        raw = _call_llm_json(provider, model, prompt, agent=f"competition_{team_id}_validator")
        review = raw if raw else mock_validator_review(decision, role=role)
        used_mock = review is raw and raw is None

    review.setdefault("review_id", f"rev_{uuid.uuid4().hex[:12]}")
    review.setdefault("decision_id", decision["decision_id"])
    review.setdefault("team_id", team_id)
    review.setdefault("created_at", now_kst_iso())

    ok, errors = validate_partner_review(review)
    if not ok:
        review = mock_validator_review(decision, role=role)
        review["reason_detail"] = f"schema_fallback: {errors}"

    append_ai_usage_log(
        {
            "log_id": f"log_{uuid.uuid4().hex[:12]}",
            "team_id": team_id,
            "role": role,
            "provider": "mock" if used_mock else provider,
            "model": model,
            "decision_id": decision["decision_id"],
            "created_at": now_kst_iso(),
        }
    )
    return review


def process_trigger(
    trigger: DecisionTrigger,
    *,
    force_mock: bool = False,
) -> dict[str, Any]:
    decision = run_main_decision(trigger, force_mock=force_mock)
    review = run_partner_or_validator(decision, force_mock=force_mock)
    return {"decision": decision, "review": review}
