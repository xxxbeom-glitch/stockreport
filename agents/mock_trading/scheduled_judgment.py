# -*- coding: utf-8 -*-
"""정기 AI 판단 (월·목·금 15:30 이후) → 실행 대기열 또는 추천만 갱신."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.judgment_pipeline import run_agent_judgment
from agents.mock_trading.judgment_runs_store import judgment_run_id, save_run
from agents.mock_trading.kis_market_watch import is_nxt_aftermarket_tradeable
from agents.mock_trading.pending_executions_store import (
    enqueue_limit_order,
    has_open_order_for_ticker,
    mark_no_buy_judgment,
)
from agents.mock_trading.trading_calendar import (
    judgment_window_open,
    now_kst,
    plan_regular_execution,
    resolve_regular_entry_type,
)
from agents.mock_trading.virtual_buy_service import append_recommendation_only, has_holding

KST = ZoneInfo("Asia/Seoul")


def run_scheduled_judgment(
    *,
    entry_type: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    at: datetime | None = None,
) -> dict[str, Any]:
    at = (at or now_kst()).astimezone(KST)
    resolved = resolve_regular_entry_type(at, force=entry_type)
    if not resolved:
        return {
            "ok": False,
            "error": "not_regular_judgment_day",
            "weekday": at.weekday(),
        }
    if not force and not judgment_window_open(at):
        return {
            "ok": False,
            "error": "judgment_window_closed",
            "hint": "정규장 마감 후 15:30 이후에 실행",
            "entry_type": resolved,
        }

    rid = judgment_run_id(resolved, at)
    judgment = run_agent_judgment(dry_run=dry_run)
    picks = list(judgment.get("passed_picks") or [])

    queued: list[dict[str, Any]] = []
    recommendation_only: list[dict[str, Any]] = []

    for pick in picks:
        ticker = str(pick.get("ticker") or "").zfill(6)
        if not ticker:
            continue
        if has_holding(ticker):
            if not dry_run:
                rec = append_recommendation_only(
                    ticker,
                    agent_keys=list(pick.get("agent_keys") or []),
                    agent_names=list(pick.get("agent_names") or []),
                    entry_type=resolved,
                    trigger_type="REGULAR",
                    trigger_reason=list(pick.get("trigger_reason") or []),
                    signal_at=str(pick.get("signal_at") or ""),
                )
                recommendation_only.append({"ticker": ticker, "result": rec})
            else:
                recommendation_only.append({"ticker": ticker, "dry_run": True})
            continue

        limit_price = int(pick.get("limit_price") or 0)
        if limit_price <= 0:
            continue

        if has_open_order_for_ticker(ticker):
            recommendation_only.append(
                {"ticker": ticker, "skipped": "duplicate_open_order"}
            )
            continue

        nxt_ok = is_nxt_aftermarket_tradeable(ticker)
        plan = plan_regular_execution(resolved, at, nxt_available=nxt_ok)
        if dry_run:
            queued.append(
                {"ticker": ticker, "dry_run": True, "limit_price": limit_price, **plan}
            )
            continue

        placed = enqueue_limit_order(
            {
                "ticker": ticker,
                "name": pick.get("name"),
                "limit_price": limit_price,
                "entry_type": resolved,
                "trigger_type": "REGULAR",
                "first_signal_at": pick.get("signal_at"),
                "signal_price": int(pick.get("signal_price") or 0),
                "agent_keys": pick.get("agent_keys"),
                "agent_names": pick.get("agent_names"),
                "trigger_reason": pick.get("trigger_reason"),
                "judgment_run_id": rid,
                "nxt_available": nxt_ok,
                **plan,
            }
        )
        if placed.get("ok"):
            queued.append(placed.get("order") or placed)
        else:
            recommendation_only.append({"ticker": ticker, "error": placed.get("error")})

    if not picks:
        no_buy = mark_no_buy_judgment(rid, reason="no_passing_candidates")
    else:
        no_buy = None

    record: dict[str, Any] = {
        "judgment_run_id": rid,
        "entry_type": resolved,
        "trigger_type": "REGULAR",
        "judgment_at": at.isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "passed_count": len(picks),
        "orders_placed": len(queued),
        "queued_executions": len(queued),
        "recommendation_only": len(recommendation_only),
        "outcome": "NO_NEW_BUYS"
        if not picks
        else ("ORDERS_PLACED" if queued else "RECOMMENDATION_ONLY"),
        "no_buy_record": no_buy,
        "judgment": {
            "ok": judgment.get("ok"),
            "candidate_count": judgment.get("candidate_count"),
            "provider_audit": judgment.get("provider_audit"),
        },
        "queued": queued,
        "recommendation_only_detail": recommendation_only,
    }
    if not dry_run:
        save_run(record)

    return {"ok": True, **record}
