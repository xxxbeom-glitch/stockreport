"""REPLAY smoke runner — isolated from LIVE, next-day fill rule."""

from __future__ import annotations

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


def _replay_slack_summary(manifest: dict[str, Any]) -> str:
    lines = [
        "[AI 투자 경쟁앱 / REPLAY] 1일 검증 완료",
        f"기준 시점: {manifest.get('decision_at')} 장 종료 후 판단",
        f"replay_run_id: {manifest.get('replay_run_id')}",
        f"실제 주문: 없음",
        f"LIVE 계좌 반영: 없음",
        f"미래 데이터 검사: {manifest.get('leakage_summary', 'N/A')}",
        "",
    ]
    for tid in TEAM_IDS:
        t = manifest.get("teams", {}).get(tid, {})
        if t.get("fill"):
            f = t["fill"]
            lines.append(
                f"팀 {tid}: {t.get('action')} → 체결 {f.get('ticker')} "
                f"{f.get('quantity')}주 @ {int(f.get('fill_price_krw', 0)):,}원 "
                f"({f.get('fill_at')}) | 현금 {t.get('cash_krw', 0):,}원"
            )
        else:
            lines.append(
                f"팀 {tid}: {t.get('action', 'N/A')} | "
                f"상태: {t.get('status', 'no_fill')} | 현금 {t.get('cash_krw', 0):,}원"
            )
    limits = manifest.get("limitations") or []
    if limits:
        lines.append("")
        lines.append("제한: " + "; ".join(limits))
    return "\n".join(lines)


def send_replay_slack(manifest: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    import json
    import urllib.request

    message = _replay_slack_summary(manifest)
    if dry_run:
        return {"ok": True, "dry_run": True, "message": message}

    webhook = (
        os.getenv("COMPETITION_SLACK_WEBHOOK", "").strip()
        or os.getenv("SLACK_WEBHOOK_URL", "").strip()
    )
    if not webhook:
        return {"ok": False, "error": "no_webhook", "message": message}

    body = json.dumps({"text": message}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            return {"ok": resp.status < 300 and raw == "ok", "response_body": raw, "message": message}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "message": message}


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
        "team_id": team_id,
        "ticker": ticker,
        "name": name,
        "quantity": quantity,
        "fill_price_krw": fill_price,
        "fill_at": fill_at,
        "fees_krw": fee,
        **fill_meta,
        **decision.get("leakage_audit", {}),
    }
    return {"ok": True, "trade": trade}


def run_replay_smoke(
    trading_date: str = "20260522",
    *,
    force_mock: bool = False,
    send_slack: bool = True,
    slack_dry_run: bool = False,
    run_audit_ai: bool = False,
) -> dict[str, Any]:
    os.environ["COMPETITION_EXECUTION_MODE"] = "replay_smoke"
    os.environ.setdefault("COMPETITION_LIVE_SCHEDULE_DISABLED", "1")

    replay_run_id = f"replay_{trading_date}_{uuid.uuid4().hex[:8]}"
    session_id = f"{replay_run_id}_session"
    store = ReplayStore(replay_run_id)

    snapshot = build_close_snapshot(trading_date)
    if not snapshot.get("ok"):
        return {"ok": False, "replay_run_id": replay_run_id, "error": snapshot.get("error")}

    store.save_snapshot(snapshot)
    evidence_objs = [EvidenceRecord(**e) for e in snapshot["evidence_records"]]
    universe_by = snapshot["universe_by_ticker"]

    triggers = _build_triggers_from_snapshot(snapshot, session_id)
    decisions_out = run_decisions_for_triggers(triggers, force_mock=force_mock)

    accounts = initial_replay_accounts()
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

        fill_meta = {
            **replay_meta(
                replay_run_id=replay_run_id,
                as_of_from=trading_date,
                as_of_to=fill_date or trading_date,
            ),
            "decision_at": snapshot["decision_at"],
            "fill_price_source": price_src or "pykrx_open_next_session",
            "fill_is_simulated_from_real_historical_price": True,
            "actual_market_order_sent": False,
            "costs_applied": False,
            "cost_model": "costs_not_implemented",
        }

        if not fill_date:
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

        name = (row or {}).get("name", ticker)
        fill_out = _apply_fill(
            accounts,
            team_id=team_id,
            ticker=ticker,
            name=name,
            quantity=qty,
            fill_price=open_px,
            fill_at=fill_at,
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

    leakage_summary = "PASS" if all(s == "PASS" for s in leakage_statuses if s) else "LIMITED"
    if "FAIL" in leakage_statuses:
        leakage_summary = "FAIL"

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

    manifest = {
        "ok": leakage_summary != "FAIL",
        "replay_run_id": replay_run_id,
        "session_id": session_id,
        "trading_date": trading_date,
        "decision_at": snapshot["decision_at"],
        "fill_date": fill_date,
        "snapshot_id": snapshot["snapshot_id"],
        "teams": team_results,
        "accounts": accounts,
        "leakage_summary": leakage_summary,
        "code_audit_failures": code_audit_fails,
        "limitations": list(set(limitations)),
        "scout_meta": snapshot.get("scout_meta"),
        "committee": committee,
        **replay_meta(replay_run_id=replay_run_id, as_of_from=trading_date, as_of_to=fill_date or trading_date),
    }
    store.save_manifest(manifest)
    store.save_audit_report(
        {
            "leakage_summary": leakage_summary,
            "code_audit_failures": code_audit_fails,
            "limitations": limitations,
        }
    )

    if send_slack:
        manifest["slack"] = send_replay_slack(manifest, dry_run=slack_dry_run)

    return manifest
