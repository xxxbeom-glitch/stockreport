"""Decision JSON schema validation."""

from __future__ import annotations

from typing import Any

VALID_ACTIONS = frozenset(
    {"BUY", "ADD_BUY", "PARTIAL_SELL", "FULL_SELL", "HOLD", "WAIT"}
)
VALID_ORDER_TYPES = frozenset({"MARKET", "LIMIT", "NONE"})
VALID_REVIEW = frozenset({"APPROVE", "REDUCE", "HOLD", "REJECT"})
ORDER_ACTIONS = frozenset({"BUY", "ADD_BUY", "PARTIAL_SELL", "FULL_SELL"})


def validate_decision(data: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for key in (
        "decision_id",
        "team_id",
        "session_id",
        "action",
        "order_type",
        "reason_label",
    ):
        if not data.get(key):
            errors.append(f"missing_{key}")

    action = str(data.get("action") or "")
    if action not in VALID_ACTIONS:
        errors.append("invalid_action")

    order_type = str(data.get("order_type") or "")
    if order_type not in VALID_ORDER_TYPES:
        errors.append("invalid_order_type")

    if action in ORDER_ACTIONS:
        if not data.get("ticker"):
            errors.append("order_requires_ticker")
        if int(data.get("quantity") or 0) <= 0 and int(data.get("allocation_krw") or 0) <= 0:
            errors.append("order_requires_quantity_or_allocation")
        if not data.get("evidence_ids"):
            errors.append("order_requires_evidence_ids")
    else:
        if order_type != "NONE":
            errors.append("hold_wait_requires_none_order_type")

    if action in ("BUY", "ADD_BUY"):
        if not data.get("target_price"):
            errors.append("buy_requires_target_price")
        if not data.get("review_conditions"):
            errors.append("buy_requires_review_conditions")

    conf = data.get("confidence")
    if conf is not None:
        try:
            c = float(conf)
            if not 0.0 <= c <= 1.0:
                errors.append("confidence_out_of_range")
        except (TypeError, ValueError):
            errors.append("invalid_confidence")

    return len(errors) == 0, errors


def validate_partner_review(data: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    result = str(data.get("result") or "")
    if result not in VALID_REVIEW:
        errors.append("invalid_review_result")
    for key in ("review_id", "decision_id", "team_id", "reason_label"):
        if not data.get(key):
            errors.append(f"missing_{key}")
    if result in ("APPROVE", "REDUCE"):
        if int(data.get("approved_quantity") or 0) <= 0 and int(
            data.get("approved_allocation_krw") or 0
        ) <= 0:
            errors.append("approve_requires_quantity_or_allocation")
    return len(errors) == 0, errors


def normalize_decision(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out["quantity"] = int(out.get("quantity") or 0)
    out["allocation_krw"] = int(out.get("allocation_krw") or 0)
    out["evidence_ids"] = list(out.get("evidence_ids") or [])
    out["review_conditions"] = list(out.get("review_conditions") or [])
    if out.get("action") in ("HOLD", "WAIT"):
        out["order_type"] = "NONE"
        out["ticker"] = out.get("ticker")
        out["quantity"] = 0
        out["allocation_krw"] = 0
    return out
