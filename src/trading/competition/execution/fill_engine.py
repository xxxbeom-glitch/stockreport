"""Order fill engine — market/limit/partial (spec §9-3)."""

from __future__ import annotations

import uuid
from typing import Any

from src.trading.competition.execution.market_session import SessionContext, validate_session_order
from src.trading.competition.execution.pending_orders import upsert_pending_order
from src.trading.competition.execution.quote_fill import (
    limit_fillable,
    market_fill_price,
    partial_fill_quantity,
)
from src.trading.competition.models import now_kst_iso


def resolve_fill(
    decision: dict[str, Any],
    *,
    quote: dict[str, Any] | None,
    session: SessionContext,
    venue: str = "KRX",
) -> dict[str, Any]:
    """
    Determine fill price/qty or pending state.
    Returns dict with keys: status, fill_price, fill_qty, partial, reason, pending_order?
    """
    action = str(decision.get("action") or "")
    side = "buy" if action in ("BUY", "ADD_BUY") else "sell"
    order_type = str(decision.get("order_type") or "MARKET")
    qty = int(decision.get("quantity") or 0)
    ticker = str(decision.get("ticker") or "")

    ok, reason = validate_session_order(
        session=session,
        order_type=order_type,
        venue=venue,
        ticker=ticker,
        quote=quote,
    )
    if not ok:
        return {"status": "blocked", "reason": reason}

    if not quote and order_type == "MARKET":
        return {"status": "blocked", "reason": "missing_quote_for_market_fill"}

    fill_price: float | None = None
    fill_reason = ""

    if order_type == "MARKET":
        fill_price, fill_reason = market_fill_price(side=side, quote=quote)
        if fill_price is None:
            return {"status": "blocked", "reason": fill_reason}
    elif order_type == "LIMIT":
        lp = decision.get("limit_price")
        if lp is None:
            return {"status": "blocked", "reason": "missing_limit_price"}
        ok_lim, fill_price, fill_reason = limit_fillable(
            side=side, limit_price=float(lp), quote=quote
        )
        if not ok_lim:
            pending = _pending_record(decision, session, qty, venue, fill_reason)
            upsert_pending_order(pending)
            return {
                "status": "pending",
                "reason": fill_reason,
                "pending_order": pending,
            }
    else:
        return {"status": "blocked", "reason": "unsupported_order_type"}

    fill_qty, is_partial = partial_fill_quantity(qty, quote)
    if fill_qty <= 0:
        return {"status": "blocked", "reason": "zero_fill_qty"}

    result: dict[str, Any] = {
        "status": "partial" if is_partial else "filled",
        "fill_price": fill_price,
        "fill_qty": fill_qty,
        "partial": is_partial,
        "reason": fill_reason,
    }

    if is_partial:
        remaining = qty - fill_qty
        pending = _pending_record(
            decision, session, remaining, venue, "partial_fill_remainder", limit_price=decision.get("limit_price")
        )
        pending["status"] = "partial"
        pending["filled_quantity"] = fill_qty
        upsert_pending_order(pending)
        result["pending_order"] = pending

    return result


def _pending_record(
    decision: dict[str, Any],
    session: SessionContext,
    quantity: int,
    venue: str,
    reason: str,
    *,
    limit_price: float | None = None,
) -> dict[str, Any]:
    ts = now_kst_iso()
    return {
        "order_id": f"ord_{uuid.uuid4().hex[:12]}",
        "decision_id": decision.get("decision_id"),
        "team_id": decision.get("team_id"),
        "ticker": decision.get("ticker"),
        "side": "buy" if decision.get("action") in ("BUY", "ADD_BUY") else "sell",
        "quantity": quantity,
        "order_type": decision.get("order_type"),
        "limit_price": limit_price if limit_price is not None else decision.get("limit_price"),
        "venue": venue,
        "session_id": decision.get("session_id"),
        "session_kind": session.label,
        "status": "pending",
        "status_reason": reason,
        "created_at": ts,
        "updated_at": ts,
    }
