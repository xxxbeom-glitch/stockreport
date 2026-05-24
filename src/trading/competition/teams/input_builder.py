"""Build team-scoped AI input from DecisionTrigger."""

from __future__ import annotations

from typing import Any

from src.trading.competition.decision.models import DecisionTrigger
from src.trading.competition.storage.accounts import load_account
from src.trading.competition.storage.positions import load_team_positions


def build_team_input(trigger: DecisionTrigger) -> dict[str, Any]:
    """
    Team receives ONLY its own account, positions, candidates, routed events.
    Forbidden: other teams' holdings/trades, raw news full text.
    """
    team_id = trigger.team_id
    account = load_account(team_id)
    positions = load_team_positions(team_id)

    held = [
        {
            "ticker": p.ticker,
            "name": p.name,
            "quantity": p.quantity,
            "avg_price_krw": p.avg_price_krw,
            "current_price_krw": p.current_price_krw,
            "eval_return_pct": p.eval_return_pct,
            "target_price_krw": p.target_price_krw,
            "buy_reason_label": p.buy_reason_label,
            "review_conditions": p.review_conditions,
            "risk_status": p.risk_status,
        }
        for p in positions.positions
        if p.quantity > 0
    ]

    payload: dict[str, Any] = {
        "team_id": team_id,
        "session_id": trigger.session_id,
        "trigger_type": trigger.trigger_type,
        "trigger_id": trigger.trigger_id,
        "account": {
            "cash_krw": account.cash_krw if account else 0,
            "total_assets_krw": account.total_assets_krw if account else 0,
            "status": account.status if account else "active",
        },
        "positions": held,
        "session_tradable": trigger.context.get("session_tradable", True),
        "evidence_ids": list(trigger.evidence_ids),
    }

    if trigger.trigger_type == "STRATEGY_CANDIDATE_REVIEW":
        payload["strategy_candidates"] = trigger.candidates
    elif trigger.trigger_type == "ACTIONABLE_EVENT_REVIEW":
        payload["actionable_events"] = {
            "event_ids": trigger.event_ids,
            "summary": trigger.summary,
            "candidates": trigger.candidates,
            "context": trigger.context,
        }
        payload["evidence_ids"] = list(
            set(payload["evidence_ids"]) | set(trigger.evidence_ids)
        )
    elif trigger.trigger_type == "POSITION_REVIEW":
        payload["positions"] = trigger.positions or held
        payload["context"] = trigger.context

    return payload
