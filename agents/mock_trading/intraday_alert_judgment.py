# -*- coding: utf-8 -*-
"""긴급 AI 판단 — INTRADAY_ALERT, 정기 회차와 분리 저장."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.intraday_alert_store import close_candidate, list_candidates
from agents.mock_trading.judgment_pipeline import run_agent_judgment
from agents.mock_trading.judgment_runs_store import judgment_run_id, save_run
from agents.mock_trading.pending_executions_store import (
    enqueue_limit_order,
    has_open_order_for_ticker,
    mark_no_buy_judgment,
)
from agents.mock_trading.trading_calendar import now_kst, plan_intraday_execution
from agents.mock_trading.virtual_buy_service import append_recommendation_only, has_holding

KST = ZoneInfo("Asia/Seoul")
ENTRY_TYPE = "INTRADAY_ALERT"


def _pick_matches_ticker(pick: dict[str, Any], ticker: str) -> bool:
    return str(pick.get("ticker") or "").zfill(6) == str(ticker).zfill(6)


def run_intraday_judgment_for_candidate(
    candidate: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    at = now_kst()
    rid = judgment_run_id(ENTRY_TYPE, at)
    ticker = str(candidate.get("ticker") or "").zfill(6)
    trigger_reason = list(candidate.get("reasons") or candidate.get("trigger_reason") or [])

    judgment = run_agent_judgment(dry_run=dry_run)
    picks = [p for p in judgment.get("passed_picks") or [] if _pick_matches_ticker(p, ticker)]
    if not picks:
        record = {
            "judgment_run_id": rid,
            "entry_type": ENTRY_TYPE,
            "trigger_type": "INTRADAY",
            "ticker": ticker,
            "outcome": "NO_NEW_BUYS",
            "no_buy_record": mark_no_buy_judgment(rid, reason="intraday_not_passed"),
            "candidate_id": candidate.get("candidate_id"),
        }
        if not dry_run:
            save_run(record)
            close_candidate(str(candidate.get("candidate_id")), status="REJECTED", detail=record)
        return {"ok": True, **record}

    pick = picks[0]
    for r in trigger_reason:
        if r not in pick.setdefault("trigger_reason", []):
            pick["trigger_reason"].append(r)

    if has_holding(ticker):
        if not dry_run:
            rec = append_recommendation_only(
                ticker,
                agent_keys=list(pick.get("agent_keys") or []),
                agent_names=list(pick.get("agent_names") or []),
                entry_type=ENTRY_TYPE,
                trigger_type="INTRADAY",
                trigger_reason=trigger_reason,
                signal_at=str(pick.get("signal_at") or ""),
            )
        else:
            rec = {"dry_run": True}
        record = {
            "judgment_run_id": rid,
            "outcome": "RECOMMENDATION_ONLY",
            "result": rec,
        }
        if not dry_run:
            save_run({**record, "entry_type": ENTRY_TYPE, "ticker": ticker})
            close_candidate(str(candidate.get("candidate_id")), status="RECOMMENDATION_ONLY", detail=record)
        return {"ok": True, **record}

    limit_price = int(pick.get("limit_price") or 0)
    if limit_price <= 0:
        record = {
            "judgment_run_id": rid,
            "entry_type": ENTRY_TYPE,
            "ticker": ticker,
            "outcome": "NO_NEW_BUYS",
            "reason": "limit_price_missing",
        }
        if not dry_run:
            save_run(record)
            close_candidate(str(candidate.get("candidate_id")), status="REJECTED", detail=record)
        return {"ok": True, **record}

    if has_open_order_for_ticker(ticker):
        record = {
            "judgment_run_id": rid,
            "outcome": "SKIPPED_DUPLICATE_ORDER",
            "ticker": ticker,
        }
        if not dry_run:
            close_candidate(str(candidate.get("candidate_id")), status="SKIPPED", detail=record)
        return {"ok": True, **record}

    plan = plan_intraday_execution(at)
    if dry_run:
        queued = {"ticker": ticker, "dry_run": True, "limit_price": limit_price, **plan}
    else:
        placed = enqueue_limit_order(
            {
                "ticker": ticker,
                "name": pick.get("name"),
                "limit_price": limit_price,
                "entry_type": ENTRY_TYPE,
                "trigger_type": "INTRADAY",
                "first_signal_at": pick.get("signal_at"),
                "signal_price": int(pick.get("signal_price") or 0),
                "agent_keys": pick.get("agent_keys"),
                "agent_names": pick.get("agent_names"),
                "trigger_reason": trigger_reason,
                "judgment_run_id": rid,
                **plan,
            }
        )
        queued = placed.get("order") if placed.get("ok") else placed

    record = {
        "judgment_run_id": rid,
        "entry_type": ENTRY_TYPE,
        "trigger_type": "INTRADAY",
        "ticker": ticker,
        "outcome": "ORDER_PLACED" if not dry_run else "DRY_RUN",
        "queued": queued,
        "candidate_id": candidate.get("candidate_id"),
    }
    if not dry_run:
        save_run(record)
        close_candidate(str(candidate.get("candidate_id")), status="DONE", detail=record)
    return {"ok": True, **record}


def process_open_intraday_candidates(*, dry_run: bool = False, limit: int = 5) -> dict[str, Any]:
    open_rows = list_candidates(status="OPEN")[:limit]
    results = []
    for cand in open_rows:
        results.append(run_intraday_judgment_for_candidate(cand, dry_run=dry_run))
    return {"ok": True, "processed": len(results), "results": results}
