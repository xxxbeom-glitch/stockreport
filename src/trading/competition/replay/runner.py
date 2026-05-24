"""REPLAY runner — isolated from LIVE, next-day fill rule."""

from __future__ import annotations

import copy
import os
import uuid
from typing import Any

from src.trading.competition.constants import TEAM_IDS
from src.trading.competition.decision.models import DecisionTrigger
from src.trading.competition.replay.code_auditor import audit_decision_proposal, initial_replay_accounts
from src.trading.competition.replay.evidence import EvidenceRecord
from src.trading.competition.replay.leakage_audit import attach_leakage_audit, audit_evidence_list
from src.trading.competition.replay.market_data import fill_price_krw, next_trading_date_after
from src.trading.competition.replay.snapshot_builder import build_close_snapshot, decision_at_iso
from src.trading.competition.replay.store import ReplayStore
from src.trading.competition.runtime import replay_meta
from src.trading.competition.teams.pipeline import run_decisions_for_triggers


def _build_triggers_from_snapshot(snapshot: dict[str, Any], session_id: str) -> list[DecisionTrigger]:
    triggers: list[DecisionTrigger] = []
    trading_date = snapshot["trading_date"]
    for team_id in TEAM_IDS:
        cands = snapshot["team_scouts"].get(team_id) or []
        for c in cands:
            c["evidence_ids"] = [f"scout:{team_id}:{c['ticker']}:{trading_date}"]
        triggers.append(
            DecisionTrigger(
                trigger_id=f"replay_{uuid.uuid4().hex[:10]}",
                trigger_type="STRATEGY_CANDIDATE_REVIEW",
                team_id=team_id,
                session_id=session_id,
                summary=f"REPLAY snapshot {snapshot['snapshot_id']}",
                candidates=cands,
                evidence_ids=[e for c in cands for e in c.get("evidence_ids", [])],
                context={
                    "replay_snapshot_id": snapshot["snapshot_id"],
                    "decision_at": snapshot["decision_at"],
                    "session_tradable": True,
                    "no_web_search": True,
                    "snapshot_only": True,
                },
            )
        )
    return triggers


def _apply_fill(
    accounts: dict[str, dict[str, Any]],
    *,
    team_id: str,
    ticker: str,
    name: str,
    quantity: int,
    fill_price: int,
    fill_at: str,
    fill_date: str,
    decision: dict[str, Any],
    fill_meta: dict[str, Any],
) -> dict[str, Any]:
    acc = accounts[team_id]
    gross = quantity * fill_price
    fee = 0
    cost = gross + fee
    if cost > acc["cash_krw"]:
        return {"ok": False, "error": "insufficient_cash_at_fill"}

    acc["cash_krw"] -= cost
    acc["positions"].append(
        {
            "ticker": ticker,
            "name": name,
            "quantity": quantity,
            "avg_price_krw": fill_price,
            "current_price_krw": fill_price,
            "eval_return_pct": 0.0,
            "eval_pnl_krw": 0,
            "target_price_krw": decision.get("target_price"),
            "buy_reason_label": decision.get("reason_label"),
            "buy_reason_detail": decision.get("reason_detail"),
            "review_conditions": decision.get("review_conditions"),
            "evidence_ids": decision.get("evidence_ids"),
        }
    )
    pos_val = sum(p["quantity"] * p["avg_price_krw"] for p in acc["positions"])
    acc["total_assets_krw"] = acc["cash_krw"] + pos_val

    trade = {
        "trade_id": f"tr_{uuid.uuid4().hex[:10]}",
        "team_id": team_id,
        "ticker": ticker,
        "name": name,
        "quantity": quantity,
        "side": "buy",
        "fill_price_krw": fill_price,
        "fill_at": fill_at,
        "fill_date": fill_date,
        "executed_at": fill_at,
        "fees_krw": fee,
        "reason_label": decision.get("reason_label"),
        **fill_meta,
    }
    return {"ok": True, "trade": trade}


def run_replay_single_day(
    trading_date: str,
    *,
    accounts: dict[str, dict[str, Any]] | None = None,
    campaign_id: str | None = None,
    force_mock: bool = False,
    run_audit_ai: bool = False,
    sync_firestore: bool = True,
) -> dict[str, Any]:
    from src.trading.competition.replay.finalize import is_campaign_ended
    from src.trading.competition.replay.period import FULL_AUDIT_END

    if campaign_id and is_campaign_ended(campaign_id):
        return {
            "ok": False,
            "error": "campaign_ended_no_new_decisions",
            "campaign_id": campaign_id,
            "competition_status": "ended",
        }
    if trading_date > FULL_AUDIT_END:
        return {
            "ok": False,
            "error": "trading_date_after_full_audit_period",
            "trading_date": trading_date,
        }

    os.environ["COMPETITION_EXECUTION_MODE"] = "replay_smoke"
    os.environ.setdefault("COMPETITION_LIVE_SCHEDULE_DISABLED", "1")

    replay_run_id = f"replay_{trading_date}_{uuid.uuid4().hex[:8]}"
    session_id = f"{replay_run_id}_session"
    store = ReplayStore(replay_run_id)

    replay_type: str | None = None
    campaign_progress: dict[str, Any] | None = None
    if campaign_id:
        from src.trading.competition.replay.finalize import load_campaign_manifest

        camp_m = load_campaign_manifest(campaign_id)
        replay_type = str(camp_m.get("replay_type") or "") or None
        if camp_m.get("days_total") is not None:
            campaign_progress = {
                "days_completed": camp_m.get("days_completed"),
                "days_total": camp_m.get("days_total"),
                "progress_label": camp_m.get("progress_label"),
            }

    from src.trading.competition.replay.observability import (
        RunObservability,
        compute_strategy_differentiation,
        providers_configuration,
    )

    obs = RunObservability(
        replay_run_id,
        campaign_id=campaign_id,
        replay_type=replay_type,
        trading_date=trading_date,
    )
    prov = providers_configuration()
    obs.log_api_connection(
        "market_data",
        ok=prov.get("kis_configured") or prov.get("pykrx_available"),
        primary="KIS" if prov.get("kis_configured") else None,
        fallback="pykrx" if prov.get("pykrx_available") else None,
    )
    obs.log_pipeline("run_start", "ok", force_mock=force_mock)

    snapshot = build_close_snapshot(trading_date)
    if not snapshot.get("ok"):
        from src.trading.competition.replay.data_validity import format_data_invalid_reason

        enrich = snapshot.get("enrich") or {}
        universe_build = snapshot.get("universe_build") or {}
        base_err = str(enrich.get("error") or snapshot.get("error") or "snapshot_failed")
        err = format_data_invalid_reason(base=base_err, enrich=enrich if enrich else None)
        obs.log_pipeline(
            "snapshot_build",
            "error",
            error=base_err,
            detail=enrich.get("detail"),
            provider_attempts=enrich.get("provider_attempts"),
            kis_configured=enrich.get("kis_configured"),
            krx_login_required=enrich.get("krx_login_required"),
            **{k: universe_build.get(k) for k in (
                "base_universe_count",
                "base_universe_source",
                "common_stock_candidate_count",
                "security_prefilter_excluded_count",
                "kis_enrich_target_count",
                "historical_price_enriched_count",
                "price_filter_pass_count",
                "liquidity_filter_pass_count",
                "risk_filter_pass_count",
                "final_eligible_universe_count",
            ) if universe_build.get(k) is not None},
        )
        obs.finalize(
            {"ok": False, "replay_run_id": replay_run_id},
            status="failed",
            failure_summary=err,
            force_mock=force_mock,
            campaign_progress=campaign_progress,
        )
        return {
            "ok": False,
            "replay_run_id": replay_run_id,
            "error": base_err,
            "enrich": enrich,
            "failure_summary": err,
        }

    from src.trading.competition.replay.data_validity import validate_snapshot_for_replay

    snap_check = validate_snapshot_for_replay(snapshot)
    if not snap_check.get("valid"):
        err = str(snap_check.get("reason") or "data_invalid")
        obs.log_pipeline("data_validity", "error", **snap_check)
        obs.finalize(
            {"ok": False, "replay_run_id": replay_run_id, "data_validity": snap_check},
            status="data_invalid",
            failure_summary=err,
            force_mock=force_mock,
            campaign_progress=campaign_progress,
        )
        return {
            "ok": False,
            "replay_run_id": replay_run_id,
            "error": "data_invalid",
            "data_validity": snap_check,
        }

    obs.log_pipeline(
        "snapshot_build",
        "ok",
        snapshot_id=snapshot.get("snapshot_id"),
        candidate_count=len(snapshot.get("eligible_universe") or []),
        scout_candidate_count=snap_check.get("scout_candidate_count"),
        priced_universe_count=snap_check.get("priced_universe_count"),
    )

    store.save_snapshot(snapshot)
    evidence_objs = [EvidenceRecord(**e) for e in snapshot["evidence_records"]]
    universe_by = snapshot["universe_by_ticker"]

    triggers = _build_triggers_from_snapshot(snapshot, session_id)
    obs.log_pipeline("decision_triggers", "ok", trigger_count=len(triggers))
    decisions_out = run_decisions_for_triggers(triggers, force_mock=force_mock)
    obs.log_pipeline("decision_ai", "ok", decision_count=len(decisions_out))

    if accounts is None:
        accounts = initial_replay_accounts()
    else:
        accounts = copy.deepcopy(accounts)

    fill_date = next_trading_date_after(trading_date)
    limitations: list[str] = []
    if not fill_date:
        limitations.append("next_trading_date_unavailable")

    team_results: dict[str, Any] = {}
    leakage_statuses: list[str] = []
    code_audit_fails = 0

    for item in decisions_out:
        decision = dict(item["decision"])
        review = item.get("review")
        team_id = str(decision.get("team_id") or "")
        decision["decision_at"] = snapshot["decision_at"]
        decision["snapshot_id"] = snapshot["snapshot_id"]

        leak = audit_evidence_list(
            evidence_objs,
            decision_at=snapshot["decision_at"],
            core_evidence_ids=list(decision.get("evidence_ids") or []),
        )
        decision = attach_leakage_audit(decision, leak)
        leakage_statuses.append(str(leak.get("status")))

        ticker = str(decision.get("ticker") or "").zfill(6) if decision.get("ticker") else ""
        row = universe_by.get(ticker) if ticker else None
        held = len(accounts[team_id]["positions"])

        audit = audit_decision_proposal(
            decision,
            team_id=team_id,
            cash_krw=accounts[team_id]["cash_krw"],
            held_count=held,
            evidence_records=evidence_objs,
            universe_row=row,
            leakage=leak,
        )
        store.append_jsonl("audit/decisions_audit.jsonl", {"decision_id": decision.get("decision_id"), **audit})

        action = decision.get("action")
        result: dict[str, Any] = {
            "action": action,
            "decision_id": decision.get("decision_id"),
            "audit": audit,
            "cash_krw": accounts[team_id]["cash_krw"],
        }

        if action not in ("BUY", "ADD_BUY"):
            result["status"] = "no_order"
            team_results[team_id] = result
            store.append_jsonl("decisions.jsonl", decision)
            continue

        if not audit.get("ok"):
            code_audit_fails += 1
            result["status"] = "invalid_due_to_audit"
            team_results[team_id] = result
            store.append_jsonl("decisions.jsonl", decision)
            continue

        if review and str(review.get("result")) not in ("APPROVE", "REDUCE", ""):
            if team_id in ("C", "D"):
                result["status"] = f"validator_{review.get('result')}"
                team_results[team_id] = result
                store.append_jsonl("decisions.jsonl", decision)
                continue

        qty = int(decision.get("quantity") or 0)
        alloc = int(decision.get("allocation_krw") or 0)

        if not fill_date:
            fill_meta = {
                **replay_meta(
                    replay_run_id=replay_run_id,
                    as_of_from=trading_date,
                    as_of_to=trading_date,
                ),
                "decision_at": snapshot["decision_at"],
                "costs_applied": False,
                "cost_model": "costs_not_implemented",
            }
            result["status"] = "pending_fill_no_next_session_data"
            store.append_jsonl("pending_orders.jsonl", {**decision, **fill_meta, "status": "pending"})
            team_results[team_id] = result
            store.append_jsonl("decisions.jsonl", decision)
            continue

        fill_at = decision_at_iso(fill_date).replace("15:30", "09:05")
        open_px, price_src, err = fill_price_krw(ticker, fill_date)
        if not open_px:
            result["status"] = f"fill_failed:{err}"
            limitations.append(f"fill_price_missing:{ticker}:{fill_date}")
            team_results[team_id] = result
            store.append_jsonl("decisions.jsonl", decision)
            continue

        if qty <= 0 and alloc > 0:
            qty = max(1, alloc // open_px)
        if qty <= 0:
            qty = 1

        fill_meta = {
            **replay_meta(
                replay_run_id=replay_run_id,
                as_of_from=trading_date,
                as_of_to=fill_date,
            ),
            "decision_at": snapshot["decision_at"],
            "fill_at": fill_at,
            "fill_price_source": price_src,
            "fill_is_simulated_from_real_historical_price": True,
            "actual_market_order_sent": False,
            "costs_applied": False,
            "cost_model": "costs_not_implemented",
        }

        name = (row or {}).get("name", ticker)
        fill_out = _apply_fill(
            accounts,
            team_id=team_id,
            ticker=ticker,
            name=name,
            quantity=qty,
            fill_price=open_px,
            fill_at=fill_at,
            fill_date=fill_date,
            decision=decision,
            fill_meta=fill_meta,
        )
        if fill_out.get("ok"):
            trade = fill_out["trade"]
            result["fill"] = trade
            result["status"] = "filled_next_session"
            result["cash_krw"] = accounts[team_id]["cash_krw"]
            store.append_jsonl("trades.jsonl", trade)
        else:
            result["status"] = fill_out.get("error", "fill_failed")

        team_results[team_id] = result
        store.append_jsonl("decisions.jsonl", decision)
        obs.log_strategy_trace(
            team_id=team_id,
            decision=decision,
            review=review,
            audit=audit,
            fill_status=result.get("status"),
        )

    strategy_diff = compute_strategy_differentiation(decisions_out, team_results=team_results)
    obs.log_pipeline(
        "strategy_differentiation",
        "ok",
        divergence_score=strategy_diff.get("divergence_score"),
        unique_profiles=strategy_diff.get("unique_action_profiles"),
    )

    leakage_summary = "PASS" if all(s == "PASS" for s in leakage_statuses if s) else "LIMITED"
    if "FAIL" in leakage_statuses:
        leakage_summary = "FAIL"

    cost_notice = "costs_not_implemented: 수수료·세금·제비용 미반영 (LIVE 시작 전 P0)"
    if cost_notice not in limitations:
        limitations.append(cost_notice)

    committee: dict[str, Any] = {"skipped": True, "reason": "run_audit_ai=false"}
    if run_audit_ai:
        from src.trading.competition.audit.committee import run_audit_committee

        committee = run_audit_committee(
            replay_run_id=replay_run_id,
            snapshot=snapshot,
            decisions=[d["decision"] for d in decisions_out],
            team_results=team_results,
            force_mock=force_mock,
        )
        store.save_committee_report(committee)

    from src.trading.competition.replay.data_validity import (
        merge_validity_into_manifest,
        validate_replay_run_outcome,
    )

    outcome_check = validate_replay_run_outcome(
        snapshot,
        accounts=accounts,
        team_results=team_results,
    )

    manifest = {
        "ok": leakage_summary != "FAIL" and outcome_check.get("valid", True),
        "replay_run_id": replay_run_id,
        "session_id": session_id,
        "campaign_id": campaign_id,
        "trading_date": trading_date,
        "decision_at": snapshot["decision_at"],
        "fill_date": fill_date,
        "snapshot_id": snapshot["snapshot_id"],
        "teams": team_results,
        "accounts": accounts,
        "leakage_summary": leakage_summary,
        "code_audit_failures": code_audit_fails,
        "limitations": list(dict.fromkeys(limitations)),
        "cost_model": "costs_not_implemented",
        "costs_applied": False,
        "scout_meta": snapshot.get("scout_meta"),
        "committee": committee,
        **replay_meta(replay_run_id=replay_run_id, as_of_from=trading_date, as_of_to=fill_date or trading_date),
    }
    manifest = merge_validity_into_manifest(manifest, outcome_check)
    store.save_manifest(manifest)
    store.save_audit_report(
        {
            "leakage_summary": leakage_summary,
            "code_audit_failures": code_audit_fails,
            "limitations": limitations,
        }
    )

    firestore_sync = {"skipped": not sync_firestore}
    if sync_firestore:
        from src.trading.competition.dashboard.replay_payload import build_replay_dashboard_payload
        from src.trading.competition.replay.firestore_store import sync_replay_run

        try:
            payload = build_replay_dashboard_payload(replay_run_id, prefer_local=True)
            firestore_sync = sync_replay_run(
                replay_run_id,
                manifest=manifest,
                dashboard_payload=payload,
            )
        except Exception as exc:
            firestore_sync = {"ok": False, "error": str(exc)}

    manifest["firestore_sync"] = firestore_sync
    store.save_manifest(manifest)

    run_status = "completed"
    if not outcome_check.get("valid"):
        run_status = "data_invalid"
    elif leakage_summary == "FAIL":
        run_status = "failed"
    failure = None
    if not manifest.get("ok"):
        failure = manifest.get("error") or "leakage_or_audit_fail"
    obs.finalize(
        manifest,
        status=run_status,
        failure_summary=failure,
        strategy_diff=strategy_diff,
        force_mock=force_mock,
        campaign_progress=campaign_progress,
    )
    manifest["observability_status"] = run_status
    store.save_manifest(manifest)
    return manifest


def run_replay_smoke(
    trading_date: str = "20260522",
    *,
    force_mock: bool = False,
    send_slack: bool = False,
    slack_dry_run: bool = False,
    run_audit_ai: bool = False,
) -> dict[str, Any]:
    """Single-day smoke — no Slack summary (policy: report links only)."""
    _ = send_slack, slack_dry_run
    return run_replay_single_day(
        trading_date,
        force_mock=force_mock,
        run_audit_ai=run_audit_ai,
        sync_firestore=True,
    )
