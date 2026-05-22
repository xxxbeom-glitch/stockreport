# -*- coding: utf-8 -*-
"""
가상 지정가 주문 체결/미체결 판정.
- 매수 지정가: 관측가 <= limit_price 이면 limit_price 에 체결
- 세션 종료까지 미체결 → EXPIRED_UNFILLED (보유 미등록)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.entry_types import ORDER_STATUS_EXPIRED, ORDER_STATUS_FILLED
from agents.mock_trading.kis_market_watch import fetch_quote, quote_to_int_price
from agents.mock_trading.pending_executions_store import (
    list_orders_in_session,
    list_orders_to_expire,
    update_order,
)
from agents.mock_trading.virtual_buy_service import has_holding, register_from_pending_item

KST = ZoneInfo("Asia/Seoul")


def _observed_price(ticker: str) -> int:
    return quote_to_int_price(fetch_quote(ticker))


def _try_fill_order(item: dict[str, Any], *, at: datetime) -> dict[str, Any]:
    oid = str(item.get("order_id") or item.get("execution_id") or "")
    ticker = str(item.get("ticker") or "").zfill(6)
    limit_price = int(item.get("limit_price") or 0)

    if has_holding(ticker):
        update_order(
            oid,
            {
                "status": ORDER_STATUS_EXPIRED,
                "expired_reason": "already_holding",
                "message": "이미 보유 — 주문 취소(미체결 처리)",
            },
        )
        return {"order_id": oid, "ticker": ticker, "status": ORDER_STATUS_EXPIRED}

    observed = _observed_price(ticker)
    if observed <= 0 or limit_price <= 0:
        return {"order_id": oid, "ticker": ticker, "status": "WAIT", "observed": observed}

    if observed > limit_price:
        return {
            "order_id": oid,
            "ticker": ticker,
            "status": "WAIT",
            "observed": observed,
            "limit_price": limit_price,
        }

    fill_price = limit_price
    fill_at = at.isoformat(timespec="seconds")
    exec_item = {
        **item,
        "filled_at": fill_at,
        "filled_price": fill_price,
        "executed_at": fill_at,
        "execution_price": fill_price,
    }
    reg = register_from_pending_item(exec_item, price=fill_price)
    if reg.get("ok") and reg.get("action") == "new_execution":
        update_order(
            oid,
            {
                "status": ORDER_STATUS_FILLED,
                "filled_at": fill_at,
                "filled_price": fill_price,
                "fill_price": fill_price,
                "observed_price_at_fill": observed,
                "register_result": reg,
            },
        )
        return {
            "order_id": oid,
            "ticker": ticker,
            "status": ORDER_STATUS_FILLED,
            "fill_price": fill_price,
            "observed": observed,
        }

    update_order(
        oid,
        {
            "status": ORDER_STATUS_EXPIRED,
            "expired_reason": reg.get("action") or reg.get("error"),
            "register_result": reg,
        },
    )
    return {"order_id": oid, "ticker": ticker, "status": ORDER_STATUS_EXPIRED, "detail": reg}


def _expire_order(item: dict[str, Any]) -> dict[str, Any]:
    oid = str(item.get("order_id") or item.get("execution_id") or "")
    ticker = str(item.get("ticker") or "").zfill(6)
    update_order(
        oid,
        {
            "status": ORDER_STATUS_EXPIRED,
            "expired_reason": "session_ended_unfilled",
            "message": "미체결 만료",
            "expired_at": datetime.now(KST).isoformat(timespec="seconds"),
        },
    )
    return {"order_id": oid, "ticker": ticker, "status": ORDER_STATUS_EXPIRED}


def process_limit_orders(*, at: datetime | None = None) -> dict[str, Any]:
    at = (at or datetime.now(KST)).astimezone(KST)
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in list_orders_in_session(at):
        oid = str(item.get("order_id") or item.get("execution_id") or "")
        if oid in seen:
            continue
        seen.add(oid)
        results.append(_try_fill_order(item, at=at))

    for item in list_orders_to_expire(at):
        oid = str(item.get("order_id") or item.get("execution_id") or "")
        if oid in seen:
            continue
        seen.add(oid)
        last = _try_fill_order(item, at=at)
        if last.get("status") == ORDER_STATUS_FILLED:
            results.append(last)
            continue
        results.append(_expire_order(item))

    return {
        "ok": True,
        "processed_at": at.isoformat(timespec="seconds"),
        "result_count": len(results),
        "results": results,
    }


# CLI / API 하위 호환
execute_due_pending = process_limit_orders
