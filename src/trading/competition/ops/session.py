"""Full competition session orchestration."""

from __future__ import annotations

from typing import Any

from src.trading.competition.decision.pipeline import run_trigger_build
from src.trading.competition.decision.triggers import build_all_decision_triggers
from src.trading.competition.execution.accounting import capture_team_snapshots
from src.trading.competition.execution.market_session import get_session_context
from src.trading.competition.execution.pending_orders import expire_pending_orders
from src.trading.competition.execution.pipeline import process_executable_decision
from src.trading.competition.models import now_kst_iso
from src.trading.competition.ops.slack import notify_trade
from src.trading.competition.ops.weekly_report import build_weekly_report
from src.trading.competition.teams.pipeline import run_decisions_for_triggers


def run_competition_session(
    session_id: str,
    *,
    dry_run: bool = False,
    force_mock: bool = True,
    persist_triggers: bool = True,
    relax_entry_filter: bool = False,
    default_fill_price: float = 50000,
    allow_simulated_quote: bool = False,
    venue: str = "KRX",
) -> dict[str, Any]:
    """End-to-end: triggers → decisions → validate/fill → execute → expire pending → snapshot."""
    session_ctx = get_session_context()

    if persist_triggers and not dry_run:
        trigger_result = run_trigger_build(session_id, enrich_market=False)
        triggers_raw = trigger_result.get("triggers") or []
    else:
        triggers = build_all_decision_triggers(session_id, enrich_market=False)
        triggers_raw = [t.to_dict() for t in triggers]

    from src.trading.competition.decision.models import DecisionTrigger

    triggers = [DecisionTrigger(**{**t, "priority": t.get("priority", "normal")}) for t in triggers_raw]
    decisions_out = run_decisions_for_triggers(triggers, force_mock=force_mock)

    executions: list[dict[str, Any]] = []
    seen: set[str] = set()
    sim_quote = allow_simulated_quote or (dry_run and default_fill_price > 0 and relax_entry_filter)

    for item in decisions_out:
        decision = item["decision"]
        review = item.get("review")
        if relax_entry_filter:
            decision = dict(decision)
            decision["_relax_entry"] = True

        if decision.get("action") == "BUY" and decision.get("ticker"):
            decision = dict(decision)
            decision["_name"] = decision.get("_name") or decision.get("ticker")
            if not decision.get("quantity"):
                alloc = int(decision.get("allocation_krw") or 0)
                price = int(default_fill_price)
                decision["quantity"] = max(1, alloc // price) if alloc else 1

        ex = process_executable_decision(
            decision,
            review,
            session_id=session_id,
            session_tradable=session_ctx.tradable,
            seen_idempotency=seen,
            default_fill_price=default_fill_price if sim_quote else None,
            session=session_ctx,
            venue=venue,
            allow_simulated_quote=sim_quote,
        )
        if ex.get("ok") and ex.get("trade"):
            notify_trade(ex["trade"], dry_run=dry_run or force_mock)
        executions.append(ex)

    expired = expire_pending_orders(session_id)
    snapshots = capture_team_snapshots()
    weekly = build_weekly_report(force=dry_run)

    filled = sum(1 for e in executions if e.get("ok"))
    pending = sum(1 for e in executions if e.get("pending"))
    blocked = sum(1 for e in executions if e.get("blocked"))

    return {
        "ok": True,
        "session_id": session_id,
        "dry_run": dry_run,
        "session_kind": session_ctx.label,
        "session_tradable": session_ctx.tradable,
        "trigger_count": len(triggers),
        "decision_count": len(decisions_out),
        "executions_filled": filled,
        "executions_pending": pending,
        "executions_blocked": blocked,
        "executions": executions,
        "expired_pending": len(expired),
        "snapshots_captured": len(snapshots),
        "weekly_report_generated": weekly is not None,
        "finished_at": now_kst_iso(),
    }
