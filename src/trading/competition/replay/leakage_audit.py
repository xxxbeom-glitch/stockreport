"""Pre/post decision leakage audit."""

from __future__ import annotations

from typing import Any

from src.trading.competition.replay.evidence import EvidenceRecord, evidence_usable_for_decision


def audit_evidence_list(
    records: list[EvidenceRecord],
    *,
    decision_at: str,
    core_evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    future = 0
    missing_ts = 0
    blocked: list[str] = []
    core = set(core_evidence_ids or [])

    for rec in records:
        if not rec.included:
            continue
        if rec.available_at and rec.decision_at and rec.available_at > rec.decision_at:
            future += 1
            blocked.append(rec.evidence_id)
            continue
        if rec.timestamp_confidence != "verified":
            missing_ts += 1
            if rec.evidence_id in core:
                blocked.append(rec.evidence_id)
            continue
        if not evidence_usable_for_decision(rec) and rec.evidence_id in core:
            blocked.append(rec.evidence_id)

    status = "PASS"
    decision_valid = True
    if future > 0:
        status = "FAIL"
        decision_valid = False
    elif blocked and core:
        status = "FAIL"
        decision_valid = False
    elif missing_ts > 0 and core:
        status = "UNVERIFIED"
        decision_valid = False

    return {
        "status": status,
        "future_evidence_count": future,
        "missing_timestamp_count": missing_ts,
        "blocked_evidence_ids": blocked,
        "decision_valid": decision_valid,
    }


def attach_leakage_audit(decision: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    out = dict(decision)
    out["leakage_audit"] = audit
    return out
