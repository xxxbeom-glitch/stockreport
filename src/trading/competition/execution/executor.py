"""Mock order execution and account updates."""

from __future__ import annotations

import uuid
from typing import Any

from src.trading.competition.constants import MAX_POSITIONS_PER_TEAM
from src.trading.competition.models import Position, TeamAccount, now_kst_iso
from src.trading.competition.storage.accounts import load_account, save_account
from src.trading.competition.storage.config_store import load_config
from src.trading.competition.storage.journal import append_notification, append_order, append_trade
from src.trading.competition.storage.positions import load_team_positions, save_team_positions

BUY_ACTIONS = frozenset({"BUY", "ADD_BUY"})
SELL_ACTIONS = frozenset({"PARTIAL_SELL", "FULL_SELL"})


def _fees(amount: float, rate: float) -> float:
    return round(amount * rate, 0)


def _resolve_fill_price(decision: dict[str, Any], *, default: float = 50000) -> float:
    lp = decision.get("limit_price")
    if lp:
        return float(lp)
    fp = decision.get("_fill_price")
    if fp:
        return float(fp)
    qty = int(decision.get("quantity") or 1)
    alloc = int(decision.get("allocation_krw") or 0)
    if alloc > 0 and qty > 0:
        return alloc / qty
    return default


def execute_decision(
    decision: dict[str, Any],
    review: dict[str, Any] | None,
    *,
    session_id: str = "",
    fill_price: float | None = None,
    order_status: str = "filled",
    executed_at: str | None = None,
    execution_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create order + trade and update account/positions."""
    action = str(decision.get("action") or "")
    team_id = str(decision.get("team_id") or "")
    ticker = str(decision.get("ticker") or "").zfill(6)
    name = str(decision.get("_name") or ticker)

    qty = int(decision.get("quantity") or 0)
    if review and review.get("result") == "REDUCE":
        qty = int(review.get("approved_quantity") or qty)

    price = fill_price if fill_price is not None else _resolve_fill_price(decision)
    cfg = load_config()
    buy_fee = cfg.fee_buy_rate or 0.00015
    sell_fee = cfg.fee_sell_rate or 0.00015
    sell_tax = cfg.tax_sell_rate or 0.0023

    order_id = f"ord_{uuid.uuid4().hex[:12]}"
    trade_id = f"trd_{uuid.uuid4().hex[:12]}"
    ts = executed_at or now_kst_iso()
    meta = dict(execution_meta or {})

    account = load_account(team_id)
    if not account:
        return {"ok": False, "error": "account_not_found"}

    tp = load_team_positions(team_id)
    held = {p.ticker: p for p in tp.positions if p.quantity > 0}

    fee = 0.0
    tax = 0.0
    realized = None
    side = "buy"
    exec_qty = qty

    if action in BUY_ACTIONS:
        gross = qty * price
        fee = _fees(gross, buy_fee)
        total = gross + fee
        if total > account.cash_krw:
            return {"ok": False, "error": "insufficient_cash_at_execute"}

        account.cash_krw -= int(total)
        if ticker in held:
            pos = held[ticker]
            new_qty = pos.quantity + qty
            pos.avg_price_krw = (pos.avg_price_krw * pos.quantity + price * qty) / new_qty
            pos.quantity = new_qty
            pos.current_price_krw = price
            side = "add_buy"
        else:
            pos = Position(
                ticker=ticker,
                name=name,
                quantity=qty,
                avg_price_krw=price,
                current_price_krw=price,
                target_price_krw=decision.get("target_price"),
                buy_reason_label=str(decision.get("reason_label") or ""),
                buy_reason_detail=str(decision.get("reason_detail") or ""),
                review_conditions=list(decision.get("review_conditions") or []),
                evidence_ids=list(decision.get("evidence_ids") or []),
            )
            tp.positions.append(pos)
            side = "buy"

        pos.eval_pnl_krw = (price - pos.avg_price_krw) * pos.quantity
        pos.eval_return_pct = (
            (price - pos.avg_price_krw) / pos.avg_price_krw * 100 if pos.avg_price_krw else 0
        )
        realized = None
        exec_qty = qty

    elif action in SELL_ACTIONS:
        pos = held.get(ticker)
        if not pos:
            return {"ok": False, "error": "no_position"}
        sell_qty = qty if qty > 0 else pos.quantity
        if action == "FULL_SELL":
            sell_qty = pos.quantity
        gross = sell_qty * price
        fee = _fees(gross, sell_fee)
        tax = _fees(gross, sell_tax)
        net = gross - fee - tax
        realized = (price - pos.avg_price_krw) * sell_qty - fee - tax
        account.cash_krw += int(net)
        pos.quantity -= sell_qty
        side = "full_sell" if pos.quantity <= 0 else "partial_sell"
        exec_qty = sell_qty
        if pos.quantity <= 0:
            tp.positions = [p for p in tp.positions if p.ticker != ticker]
    else:
        return {"ok": False, "error": "non_executable_action"}

    # Recalc total assets
    positions_value = sum(
        p.current_price_krw * p.quantity for p in tp.positions if p.quantity > 0
    )
    account.total_assets_krw = account.cash_krw + int(positions_value)
    account.updated_at = ts
    tp.updated_at = ts

    order = {
        "order_id": order_id,
        "decision_id": decision["decision_id"],
        "team_id": team_id,
        "ticker": ticker,
        "side": "buy" if action in BUY_ACTIONS else "sell",
        "quantity": qty,
        "order_type": decision.get("order_type"),
        "limit_price": decision.get("limit_price"),
        "status": order_status,
        "status_reason": "",
        "session_id": session_id or decision.get("session_id", ""),
        "idempotency_key": decision.get("decision_id", ""),
        "created_at": ts,
        "updated_at": ts,
        **meta,
    }
    trade = {
        "trade_id": trade_id,
        "order_id": order_id,
        "team_id": team_id,
        "ticker": ticker,
        "name": name,
        "side": side,
        "quantity": exec_qty,
        "fill_price_krw": price,
        "fees_krw": fee,
        "tax_krw": tax if action in SELL_ACTIONS else 0,
        "realized_pnl_krw": realized,
        "reason_label": decision.get("reason_label", ""),
        "reason_detail": decision.get("reason_detail", ""),
        "executed_at": ts,
        **meta,
    }

    append_order(order)
    append_trade(trade)
    save_account(account)
    save_team_positions(tp)

    append_notification(
        {
            "notification_id": f"ntf_{uuid.uuid4().hex[:10]}",
            "category": "trade",
            "title": f"팀 {team_id} {side} 체결",
            "sub": f"{name} {trade['quantity']}주 @ {int(price):,}원",
            "team_id": team_id,
            "read": False,
            "created_at": ts,
        }
    )

    return {"ok": True, "order": order, "trade": trade}
