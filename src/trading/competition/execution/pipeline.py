"""Decision → validate → fill → execute pipeline."""

from __future__ import annotations

from typing import Any

from src.trading.competition.execution.executor import execute_decision
from src.trading.competition.execution.fill_engine import resolve_fill
from src.trading.competition.execution.market_session import SessionContext, get_session_context
from src.trading.competition.execution.validator import validate_order_proposal
from src.trading.competition.storage.journal import append_order


def _fetch_quote(ticker: str) -> dict[str, Any] | None:
    try:
        from data.kis_client import get_price

        return get_price(ticker.zfill(6))
    except Exception:
        return None


def process_executable_decision(
    decision: dict[str, Any],
    review: dict[str, Any] | None,
    *,
    session_id: str = "",
    session_tradable: bool = True,
    seen_idempotency: set[str] | None = None,
    default_fill_price: float | None = None,
    quote: dict[str, Any] | None = None,
    session: SessionContext | None = None,
    venue: str = "KRX",
    allow_simulated_quote: bool = False,
) -> dict[str, Any]:
    if session_id:
        decision = dict(decision)
        decision.setdefault("session_id", session_id)

    ctx = session or get_session_context()
    if not session_tradable and not ctx.tradable:
        return _blocked(decision, session_id, "session_not_tradable")

    ok, reason = validate_order_proposal(
        decision,
        review,
        session_tradable=ctx.tradable,
        seen_idempotency=seen_idempotency,
        session=ctx,
        venue=venue,
        quote=quote,
    )
    if not ok:
        return _blocked(decision, session_id, reason)

    ticker = str(decision.get("ticker") or "").zfill(6)
    q = quote or decision.get("_quote")
    if q is None and not allow_simulated_quote:
        q = _fetch_quote(ticker)
    elif q is None and allow_simulated_quote and default_fill_price:
        side = "buy" if decision.get("action") in ("BUY", "ADD_BUY") else "sell"
        q = {
            "price": default_fill_price,
            "ask_price": default_fill_price,
            "bid_price": default_fill_price,
            "available_qty": int(decision.get("quantity") or 1),
        }

    fill = resolve_fill(decision, quote=q, session=ctx, venue=venue)
    status = fill.get("status")

    if status == "blocked":
        return _blocked(decision, session_id, str(fill.get("reason")))

    if status == "pending":
        po = fill.get("pending_order") or {}
        append_order({**po, "status": "pending"})
        return {"ok": False, "pending": True, "reason": fill.get("reason"), "order": po}

    fill_price = fill.get("fill_price")
    fill_qty = int(fill.get("fill_qty") or 0)
    if fill_price is None or fill_qty <= 0:
        return _blocked(decision, session_id, "fill_confirmation_failed")

    exec_decision = dict(decision)
    exec_decision["quantity"] = fill_qty
    exec_decision["_fill_price"] = fill_price
    exec_decision["_name"] = exec_decision.get("_name") or ticker

    result = execute_decision(
        exec_decision,
        review,
        session_id=session_id or decision.get("session_id", ""),
        fill_price=float(fill_price),
        order_status="partial" if fill.get("partial") else "filled",
    )
    if fill.get("partial"):
        result["partial"] = True
        result["pending_order_unfilled"] = fill.get("pending_order")
    return result


def _blocked(decision: dict[str, Any], session_id: str, reason: str) -> dict[str, Any]:
    blocked = {
        "order_id": f"blocked_{decision.get('decision_id', '')}",
        "decision_id": decision.get("decision_id"),
        "team_id": decision.get("team_id"),
        "ticker": decision.get("ticker"),
        "side": "buy" if decision.get("action") in ("BUY", "ADD_BUY") else "sell",
        "quantity": decision.get("quantity"),
        "order_type": decision.get("order_type"),
        "limit_price": decision.get("limit_price"),
        "status": "blocked",
        "status_reason": reason,
        "session_id": session_id,
        "idempotency_key": decision.get("decision_id", ""),
    }
    append_order(blocked)
    return {"ok": False, "blocked": True, "reason": reason, "order": blocked}
