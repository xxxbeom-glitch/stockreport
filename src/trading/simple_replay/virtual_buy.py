"""Next-session open virtual buy for SIMPLE_REPLAY."""

from __future__ import annotations

from typing import Any

from src.trading.competition.replay.market_data import fill_price_krw
from src.trading.simple_replay.constants import INITIAL_CASH_KRW
from src.trading.simple_replay.errors import SimpleReplayError


def virtual_buy(
    decision: dict[str, Any],
    *,
    buy_date: str,
    name_by_ticker: dict[str, str],
) -> dict[str, Any] | None:
    if decision.get("action") != "BUY":
        return None

    sel = decision.get("selected_stock") or {}
    ticker = str(sel.get("stock_code") or "").zfill(6)
    if not ticker:
        return None

    price, source, err = fill_price_krw(ticker, buy_date)
    if not price or price <= 0:
        raise SimpleReplayError("buy_price_missing", detail=f"{ticker}:{buy_date}:{err}")

    qty = INITIAL_CASH_KRW // price
    if qty <= 0:
        decision["action"] = "SKIP"
        decision["skip_reason"] = "insufficient_cash_for_one_share"
        return None

    invested = qty * price
    return {
        "team_id": decision["team_id"],
        "ticker": ticker,
        "name": sel.get("stock_name") or name_by_ticker.get(ticker, ticker),
        "buy_date": buy_date,
        "buy_price": price,
        "quantity": qty,
        "invested_amount": invested,
        "remaining_cash": INITIAL_CASH_KRW - invested,
        "target_price": decision.get("target_price"),
        "reason_label": decision.get("reason_label"),
        "fill_source": source,
    }
