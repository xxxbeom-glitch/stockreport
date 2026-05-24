"""Mock LLM provider for dry-run and tests."""

from __future__ import annotations

import uuid
from typing import Any

from src.trading.competition.models import now_kst_iso


def mock_main_decision(team_input: dict[str, Any], *, role: str) -> dict[str, Any]:
    """Deterministic mock decision based on trigger context."""
    team_id = team_input["team_id"]
    session_id = team_input["session_id"]
    trigger_type = team_input["trigger_type"]
    cash = int((team_input.get("account") or {}).get("cash_krw") or 0)
    positions = team_input.get("positions") or []
    evidence = list(team_input.get("evidence_ids") or [])

    action = "HOLD"
    ticker = None
    qty = 0
    alloc = 0
    order_type = "NONE"
    target = None
    review_conds: list[str] = []
    reason = f"mock_{trigger_type.lower()}"
    detail = "mock provider — no live LLM"

    if trigger_type == "STRATEGY_CANDIDATE_REVIEW":
        cands = team_input.get("strategy_candidates") or []
        if cands and cash >= 50000 and len(positions) < 3:
            top = cands[0]
            ticker = top.get("ticker")
            action = "BUY"
            order_type = "MARKET"
            price = int(top.get("metrics", {}).get("current_price_krw") or 50000)
            if price <= 0:
                price = 50000
            qty = max(1, min(5, cash // price))
            alloc = qty * price
            target = float(price * 1.08)
            review_conds = ["mock: -5% 손절", "mock: 목표가 도달 시 재검토"]
            evidence = evidence or [f"scout:{ticker}"]
            reason = top.get("reason_label", "strategy_candidate")
    elif trigger_type == "POSITION_REVIEW" and positions:
        action = "HOLD"
        reason = "position_review_hold"
    elif trigger_type == "ACTIONABLE_EVENT_REVIEW":
        action = "WAIT"
        reason = "event_review_wait"

    return {
        "decision_id": f"dec_{uuid.uuid4().hex[:12]}",
        "team_id": team_id,
        "session_id": session_id,
        "trigger_type": trigger_type,
        "trigger_event_ids": team_input.get("actionable_events", {}).get("event_ids", [])
        if trigger_type == "ACTIONABLE_EVENT_REVIEW"
        else [],
        "action": action,
        "ticker": ticker,
        "quantity": qty,
        "allocation_krw": alloc,
        "order_type": order_type,
        "limit_price": None,
        "target_price": target,
        "reason_label": reason,
        "reason_detail": detail,
        "review_conditions": review_conds,
        "evidence_ids": evidence,
        "confidence": 0.55 if action in ("BUY", "ADD_BUY") else 0.4,
        "created_at": now_kst_iso(),
        "_mock_role": role,
    }


def mock_partner_note(decision: dict[str, Any], *, role: str) -> dict[str, Any] | None:
    """A/B partner — note only when order action."""
    if decision.get("action") not in ("BUY", "ADD_BUY", "PARTIAL_SELL", "FULL_SELL"):
        return None
    return {
        "note_id": f"note_{uuid.uuid4().hex[:8]}",
        "decision_id": decision["decision_id"],
        "team_id": decision["team_id"],
        "role": role,
        "note": "mock partner confirmation — no veto",
        "created_at": now_kst_iso(),
    }


def mock_validator_review(decision: dict[str, Any], *, role: str) -> dict[str, Any]:
    """C/D validator — APPROVE mock buys, HOLD otherwise."""
    action = decision.get("action")
    if action in ("BUY", "ADD_BUY"):
        result = "APPROVE"
        qty = int(decision.get("quantity") or 0)
        alloc = int(decision.get("allocation_krw") or 0)
    elif action in ("PARTIAL_SELL", "FULL_SELL"):
        result = "APPROVE"
        qty = int(decision.get("quantity") or 0)
        alloc = 0
    else:
        result = "HOLD"
        qty = 0
        alloc = 0

    return {
        "review_id": f"rev_{uuid.uuid4().hex[:12]}",
        "decision_id": decision["decision_id"],
        "team_id": decision["team_id"],
        "result": result,
        "approved_quantity": qty,
        "approved_allocation_krw": alloc,
        "reason_label": f"mock_validator_{result.lower()}",
        "reason_detail": f"mock validator ({role})",
        "risk_evidence_ids": list(decision.get("evidence_ids") or []),
        "created_at": now_kst_iso(),
    }
