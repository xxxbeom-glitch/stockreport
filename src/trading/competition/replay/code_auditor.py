"""Code auditor — rule violations before replay decisions/orders."""

from __future__ import annotations

from typing import Any

from src.trading.competition.constants import (
    INITIAL_CASH_KRW,
    MAX_ENTRY_PRICE_KRW,
    MAX_POSITIONS_PER_TEAM,
    MIN_AVG_TRADING_VALUE_KRW,
)
from src.trading.competition.replay.leakage_audit import audit_evidence_list
from src.trading.competition.replay.evidence import EvidenceRecord


def audit_decision_proposal(
    decision: dict[str, Any],
    *,
    team_id: str,
    cash_krw: int,
    held_count: int,
    evidence_records: list[EvidenceRecord],
    universe_row: dict[str, Any] | None,
    leakage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return {ok, status, reasons[]}. FAIL blocks execution."""
    reasons: list[str] = []
    action = str(decision.get("action") or "")

    leak = leakage or audit_evidence_list(
        evidence_records,
        decision_at=str(decision.get("decision_at") or ""),
        core_evidence_ids=list(decision.get("evidence_ids") or []),
    )
    if not leak.get("decision_valid"):
        reasons.append(f"leakage_audit:{leak.get('status')}")

    if action in ("BUY", "ADD_BUY"):
        if not decision.get("evidence_ids"):
            reasons.append("missing_evidence_ids")
        ticker = str(decision.get("ticker") or "").zfill(6)
        qty = int(decision.get("quantity") or 0)
        alloc = int(decision.get("allocation_krw") or 0)
        price = int(
            (universe_row or {}).get("current_price_krw")
            or decision.get("_fill_price")
            or 0
        )
        cost = alloc if alloc > 0 else qty * price
        if cost > cash_krw:
            reasons.append("insufficient_cash")
        if action == "BUY" and held_count >= MAX_POSITIONS_PER_TEAM:
            reasons.append("max_positions_exceeded")
        if universe_row:
            if int(universe_row.get("current_price_krw") or 0) > MAX_ENTRY_PRICE_KRW:
                reasons.append("price_cap_exceeded")
            avg_tv = int(universe_row.get("avg_trading_value_20d_krw") or 0)
            if avg_tv < MIN_AVG_TRADING_VALUE_KRW:
                reasons.append("avg_tv_below_minimum")
            if universe_row.get("risk_exclude_new_entry"):
                reasons.append("risk_exclude_new_entry")
            if universe_row.get("filter_category") != "eligible":
                reasons.append(f"entry_filter:{universe_row.get('filter_reason')}")

    status = "PASS" if not reasons else "FAIL"
    return {"ok": status == "PASS", "status": status, "reasons": reasons, "leakage_audit": leak}


def initial_replay_accounts() -> dict[str, dict[str, Any]]:
    from src.trading.competition.constants import TEAM_IDS

    return {
        tid: {
            "team_id": tid,
            "cash_krw": INITIAL_CASH_KRW,
            "total_assets_krw": INITIAL_CASH_KRW,
            "positions": [],
        }
        for tid in TEAM_IDS
    }
