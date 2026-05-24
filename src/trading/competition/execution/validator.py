"""Order validation (spec §9-4)."""

from __future__ import annotations

from typing import Any

from src.trading.competition.constants import MAX_ENTRY_PRICE_KRW, MAX_POSITIONS_PER_TEAM
from src.trading.competition.execution.market_session import SessionContext, validate_session_order
from src.trading.competition.storage.accounts import load_account
from src.trading.competition.storage.positions import load_team_positions
from src.trading.competition.universe.builder import evaluate_entry_eligibility, load_eligible_universe

BUY_ACTIONS = frozenset({"BUY", "ADD_BUY"})
SELL_ACTIONS = frozenset({"PARTIAL_SELL", "FULL_SELL"})


def _held_tickers(team_id: str) -> dict[str, Any]:
    tp = load_team_positions(team_id)
    return {p.ticker: p for p in tp.positions if p.quantity > 0}


def validate_order_proposal(
    decision: dict[str, Any],
    review: dict[str, Any] | None,
    *,
    session_tradable: bool = True,
    seen_idempotency: set[str] | None = None,
    session: SessionContext | None = None,
    venue: str = "KRX",
    quote: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    action = str(decision.get("action") or "")
    if action in ("HOLD", "WAIT"):
        return False, "no_order_action"

    team_id = str(decision.get("team_id") or "")
    if team_id in ("C", "D"):
        if not review:
            return False, "verify_team_missing_review"
        if review.get("result") not in ("APPROVE", "REDUCE"):
            return False, f"verify_team_{review.get('result')}"

    ticker = str(decision.get("ticker") or "").zfill(6)
    if not ticker:
        return False, "missing_ticker"

    qty = int(decision.get("quantity") or 0)
    alloc = int(decision.get("allocation_krw") or 0)
    if review and review.get("result") == "REDUCE":
        qty = int(review.get("approved_quantity") or qty)
        alloc = int(review.get("approved_allocation_krw") or alloc)

    if qty <= 0 and alloc <= 0:
        return False, "zero_quantity"

    if not decision.get("evidence_ids"):
        return False, "missing_evidence_ids"

    if not session_tradable:
        return False, "session_not_tradable"

    idem = str(decision.get("decision_id") or "")
    if seen_idempotency is not None and idem in seen_idempotency:
        return False, "duplicate_decision"
    if seen_idempotency is not None:
        seen_idempotency.add(idem)

    account = load_account(team_id)
    cash = account.cash_krw if account else 0
    held = _held_tickers(team_id)

    order_type = str(decision.get("order_type") or "NONE")
    if order_type not in ("MARKET", "LIMIT"):
        return False, "invalid_order_type"

    if session is not None:
        ok_sess, sess_reason = validate_session_order(
            session=session,
            order_type=order_type,
            venue=venue,
            ticker=ticker,
            quote=quote or decision.get("_quote"),
        )
        if not ok_sess:
            return False, sess_reason

    if action in BUY_ACTIONS:
        if ticker in held and action == "BUY":
            return False, "already_held_use_add_buy"
        if ticker not in held and len(held) >= MAX_POSITIONS_PER_TEAM:
            return False, "max_positions_exceeded"

        price = int(decision.get("limit_price") or decision.get("_fill_price") or 0)
        if price <= 0:
            price = max(1, alloc // max(qty, 1)) if qty else MAX_ENTRY_PRICE_KRW
        cost = alloc if alloc > 0 else qty * price
        if cost > cash:
            return False, "insufficient_cash"
        if price > MAX_ENTRY_PRICE_KRW and ticker not in held:
            return False, "price_cap_exceeded"

        rec = None
        for row in load_eligible_universe():
            if str(row.get("ticker", "")).zfill(6) == ticker:
                rec = row
                break
        if rec and ticker not in held and not decision.get("_relax_entry"):
            ok_elig, reason, _cat = evaluate_entry_eligibility(rec)
            if not ok_elig:
                return False, f"entry_filter:{reason}"

    if action in SELL_ACTIONS:
        pos = held.get(ticker)
        if not pos:
            return False, "no_position_to_sell"
        sell_qty = qty if qty > 0 else pos.quantity
        if sell_qty > pos.quantity:
            return False, "sell_exceeds_holding"
        if action == "FULL_SELL" and sell_qty < pos.quantity:
            return False, "full_sell_qty_mismatch"

    return True, "ok"
