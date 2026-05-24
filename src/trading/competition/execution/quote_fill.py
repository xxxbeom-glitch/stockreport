"""Quote-based fill pricing (spec §9-3)."""

from __future__ import annotations

from typing import Any


def _num(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return None


def extract_quote_prices(quote: dict[str, Any] | None) -> dict[str, Any]:
    """
    Parse best bid/ask from KIS inquire-price raw or explicit test fields.
    Returns empty dict if quote missing — caller must block fill.
    """
    if not quote:
        return {}
    raw = quote.get("raw") or {}
    bid = _num(quote.get("bid_price")) or _num(raw.get("bidp")) or _num(raw.get("stck_bidp"))
    ask = _num(quote.get("ask_price")) or _num(raw.get("askp")) or _num(raw.get("stck_askp"))
    last = _num(quote.get("price")) or _num(raw.get("stck_prpr"))
    avail = int(quote.get("available_qty") or raw.get("available_qty") or 0)
    return {
        "bid_price": bid,
        "ask_price": ask,
        "last_price": last,
        "available_qty": avail,
        "nxt_eligible": quote.get("nxt_eligible"),
        "raw": raw,
    }


def market_fill_price(*, side: str, quote: dict[str, Any] | None) -> tuple[float | None, str]:
    """Market buy at ask, sell at bid. No quote → no fill."""
    px = extract_quote_prices(quote)
    if side == "buy":
        price = px.get("ask_price") or px.get("last_price")
        if price is None:
            return None, "missing_ask_or_last_price"
        return float(price), "market_at_ask"
    price = px.get("bid_price") or px.get("last_price")
    if price is None:
        return None, "missing_bid_or_last_price"
    return float(price), "market_at_bid"


def limit_fillable(
    *,
    side: str,
    limit_price: float,
    quote: dict[str, Any] | None,
) -> tuple[bool, float | None, str]:
    """
    Limit buy fills when limit >= ask (or last if ask missing).
    Limit sell fills when limit <= bid (or last if bid missing).
    """
    px = extract_quote_prices(quote)
    if side == "buy":
        ask = px.get("ask_price") or px.get("last_price")
        if ask is None:
            return False, None, "missing_ask_for_limit_buy"
        if limit_price >= ask:
            return True, float(ask), "limit_buy_crossed_ask"
        return False, None, "limit_buy_not_marketable"
    bid = px.get("bid_price") or px.get("last_price")
    if bid is None:
        return False, None, "missing_bid_for_limit_sell"
    if limit_price <= bid:
        return True, float(bid), "limit_sell_crossed_bid"
    return False, None, "limit_sell_not_marketable"


def partial_fill_quantity(requested: int, quote: dict[str, Any] | None) -> tuple[int, bool]:
    """Partial fill when available_qty < requested (spec §9-3)."""
    if requested <= 0:
        return 0, False
    px = extract_quote_prices(quote)
    avail = int(px.get("available_qty") or 0)
    if avail <= 0:
        return requested, False
    if avail >= requested:
        return requested, False
    return avail, True
