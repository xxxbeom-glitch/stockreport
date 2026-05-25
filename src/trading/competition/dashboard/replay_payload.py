"""REPLAY-only dashboard payload (never reads LIVE competition files)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS, TEAM_META, TEAM_TO_AGENT
from src.trading.competition.replay.firestore_store import (
    list_replay_runs_firestore,
    load_replay_run_firestore,
)
from src.trading.competition.replay.reports import load_campaign_reports
from src.trading.competition.runtime import COMPETITION_ROOT, replay_run_dir

REPLAY_ROOT = COMPETITION_ROOT / "replay"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _return_pct(initial: int, current: int) -> float:
    if initial <= 0:
        return 0.0
    return round((current - initial) / initial * 100, 2)


def _badge_css(badge_class: str) -> str:
    if badge_class in ("speed", "verify"):
        return f"badge--{badge_class}"
    return badge_class if badge_class.startswith("badge--") else "badge--speed"


def _agent_display_name(team_id: str) -> str:
    try:
        idx = TEAM_IDS.index(team_id) + 1
    except ValueError:
        idx = 1
    return f"에이전트 {idx}호"


def _display_reason(label: Any, detail: Any = None) -> str:
    lbl = str(label or "").strip()
    det = str(detail or "").strip()
    if not lbl and not det:
        return "-"
    low = det.lower()
    if "mock provider" in low or low.startswith("mock:") or low.startswith("mock "):
        return lbl or "-"
    return lbl or det or "-"


def _is_executed_trade(tr: dict[str, Any]) -> bool:
    if int(tr.get("quantity") or 0) <= 0:
        return False
    if int(tr.get("fill_price_krw") or 0) <= 0:
        return False
    if not (tr.get("trade_id") or tr.get("executed_at") or tr.get("fill_at")):
        return False
    return True


def _prefer_firestore() -> bool:
    return os.getenv("COMPETITION_REPLAY_READ_FIRESTORE", "1").lower() in ("1", "true", "yes")


def list_replay_runs() -> list[dict[str, Any]]:
    seen: set[str] = set()
    runs: list[dict[str, Any]] = []

    if _prefer_firestore():
        for doc in list_replay_runs_firestore():
            rid = doc.get("replay_run_id") or doc.get("manifest", {}).get("replay_run_id")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            m = doc.get("manifest") or doc
            runs.append(
                {
                    "replayRunId": rid,
                    "tradingDate": m.get("trading_date"),
                    "decisionAt": m.get("decision_at"),
                    "fillDate": m.get("fill_date"),
                    "leakageSummary": m.get("leakage_summary"),
                    "executionMode": m.get("execution_mode"),
                    "campaignId": m.get("campaign_id"),
                    "ok": m.get("ok", True),
                    "source": "firestore",
                }
            )

    if REPLAY_ROOT.is_dir():
        for manifest_path in REPLAY_ROOT.glob("*/manifest.json"):
            manifest = _read_json(manifest_path)
            rid = manifest.get("replay_run_id")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            runs.append(
                {
                    "replayRunId": rid,
                    "tradingDate": manifest.get("trading_date"),
                    "decisionAt": manifest.get("decision_at"),
                    "fillDate": manifest.get("fill_date"),
                    "leakageSummary": manifest.get("leakage_summary"),
                    "executionMode": manifest.get("execution_mode"),
                    "campaignId": manifest.get("campaign_id"),
                    "ok": manifest.get("ok", True),
                    "source": "local",
                }
            )

    runs.sort(key=lambda r: (r.get("tradingDate") or "", r.get("replayRunId") or ""), reverse=True)
    return runs


def _ticker_name_map(snapshot: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for key in ("eligible_universe", "universe", "candidates"):
        for row in snapshot.get(key) or []:
            if isinstance(row, dict) and row.get("ticker"):
                names[str(row["ticker"])] = str(row.get("name") or row["ticker"])
    return names


def _build_audit_summary(manifest: dict[str, Any], code_audit: dict[str, Any]) -> dict[str, Any]:
    committee = manifest.get("committee") or {}
    leakage = manifest.get("leakage_summary") or code_audit.get("leakage_summary") or "UNVERIFIED"
    code_failures = manifest.get("code_audit_failures")
    if code_failures is None:
        code_failures = code_audit.get("code_audit_failures", 0)

    committee_status = "not_implemented"
    committee_verdict = None
    if committee.get("skipped"):
        committee_status = "skipped"
        committee_verdict = committee.get("reason") or "run_audit_ai=false"
    elif committee.get("verdict"):
        committee_status = "completed"
        committee_verdict = committee.get("verdict")
    elif committee.get("lead") or committee.get("challenger"):
        committee_status = "completed"
        committee_verdict = committee.get("summary") or committee.get("conclusion")

    cost_model = str(manifest.get("cost_model") or code_audit.get("cost_model") or "costs_not_implemented")
    costs_not_implemented = cost_model == "costs_not_implemented" or manifest.get("costs_applied") is False
    live_ready = (
        leakage == "PASS"
        and int(code_failures or 0) == 0
        and not manifest.get("reset_required_before_live")
        and not costs_not_implemented
    )
    limitations = list(manifest.get("limitations") or code_audit.get("limitations") or [])
    costs_warning = (
        "매매 수수료·세금·제비용 미반영 — REPLAY 총자산·수익률은 비용 제외 기준 (LIVE 시작 전 P0)"
        if costs_not_implemented
        else None
    )

    return {
        "leakageStatus": leakage,
        "ruleViolationCount": int(code_failures or 0),
        "committeeStatus": committee_status,
        "committeeVerdict": committee_verdict,
        "liveReady": live_ready,
        "costModel": cost_model,
        "costsWarning": costs_warning,
        "limitations": limitations,
        "affectsLiveAccount": manifest.get("affects_live_account", False),
    }


def _build_from_manifest(
    replay_run_id: str,
    manifest: dict[str, Any],
    *,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    run_dir = replay_run_dir(replay_run_id)
    snapshot = _read_json(run_dir / "snapshot.json")
    if not snapshot and manifest.get("snapshot_id"):
        snapshot = {}
    decisions = _read_jsonl(run_dir / "decisions.jsonl")
    trades = _read_jsonl(run_dir / "trades.jsonl")
    code_audit = _read_json(run_dir / "audit" / "code_audit_summary.json")
    names = _ticker_name_map(snapshot)

    accounts = manifest.get("accounts") or {}
    agent_meta: dict[str, Any] = {}
    team_decisions: list[dict[str, Any]] = []
    stock_catalog: dict[str, Any] = {}
    trade_history: dict[str, list] = {f"agent{i}": [] for i in range(1, 5)}

    decision_at = (manifest.get("decision_at") or "")[:10] or manifest.get("trading_date", "")
    fill_date = manifest.get("fill_date") or ""
    label_decision = decision_at.replace("-", ".")[5:] if decision_at else "시작"
    label_fill = fill_date[4:6] + "/" + fill_date[6:8] if len(fill_date) == 8 else "체결"

    cash_total = 0
    asset_total = 0
    best_team_return = -999.0
    best_team_key = "agent1"
    best_stock_return = -999.0
    best_stock_name = "-"
    timeline_series: list[dict[str, Any]] = []

    teams_manifest = manifest.get("teams") or {}
    cid = campaign_id or manifest.get("campaign_id")

    for tid in TEAM_IDS:
        agent_key = TEAM_TO_AGENT[tid]
        meta = TEAM_META[tid]
        acc = accounts.get(tid) or {}
        tm = teams_manifest.get(tid) or {}
        cash = int(acc.get("cash_krw") or INITIAL_CASH_KRW)
        total = int(acc.get("total_assets_krw") or cash)
        ret = _return_pct(INITIAL_CASH_KRW, total)
        cash_total += cash
        asset_total += total
        if ret > best_team_return:
            best_team_return = ret
            best_team_key = agent_key

        display = _agent_display_name(tid)
        agent_meta[agent_key] = {
            "name": display,
            "badge": meta["type_label"],
            "badgeClass": _badge_css(meta["badge_class"]),
            "strategy": meta["strategy_label"],
            "cashKrw": cash,
            "totalAssetsKrw": total,
            "returnPct": ret,
            "status": tm.get("status") or acc.get("status") or "replay",
        }

        timeline_series.append(
            {
                "key": agent_key,
                "label": display,
                "color": ["#4f8cff", "#34c759", "#ff9500", "#af52de"][TEAM_IDS.index(tid)],
                "data": [INITIAL_CASH_KRW, total],
            }
        )

        for pos in acc.get("positions") or []:
            if int(pos.get("quantity") or 0) <= 0:
                continue
            code = str(pos.get("ticker") or "")
            pname = str(pos.get("name") or names.get(code) or code)
            avg = int(pos.get("avg_price_krw") or 0)
            cur = int(pos.get("current_price_krw") or avg)
            ret_pct = float(pos.get("eval_return_pct") or 0)
            pnl = int(pos.get("eval_pnl_krw") or 0)
            if ret_pct > best_stock_return:
                best_stock_return = ret_pct
                best_stock_name = pname
            tgt = int(pos.get("target_price_krw") or 0) or None
            block = {"avg": avg, "current": cur, "returnPct": ret_pct, "pnl": pnl, "targetPrice": tgt}
            if code not in stock_catalog:
                stock_catalog[code] = {
                    "name": pname,
                    "agents": [],
                    "reason": _display_reason(pos.get("buy_reason_label"), pos.get("buy_reason_detail")),
                    "targetPrice": tgt,
                    "all": dict(block),
                    "7d": dict(block),
                    "14d": dict(block),
                }
            if agent_key not in stock_catalog[code]["agents"]:
                stock_catalog[code]["agents"].append(agent_key)

    trade_idx = 0
    for tr in trades:
        if not _is_executed_trade(tr):
            continue
        tid = tr.get("team_id", "A")
        agent_key = TEAM_TO_AGENT.get(tid, "agent1")
        code = str(tr.get("ticker") or "")
        trade_history[agent_key].append(
            {
                "dayIndex": trade_idx,
                "date": (tr.get("executed_at") or tr.get("fill_at") or fill_date or "")[:10],
                "name": tr.get("name") or names.get(code) or code,
                "code": code,
                "side": "sell" if "sell" in str(tr.get("side", "")).lower() else "buy",
                "price": tr.get("fill_price_krw"),
                "qty": tr.get("quantity"),
                "pnl": tr.get("realized_pnl_krw"),
                "reason": _display_reason(tr.get("reason_label"), tr.get("reason_detail")),
                "fillDate": tr.get("fill_date") or fill_date,
                "historical": True,
            }
        )
        trade_idx += 1

    for dec in decisions:
        tid = dec.get("team_id", "A")
        agent_key = TEAM_TO_AGENT.get(tid, "agent1")
        ticker = dec.get("ticker")
        leakage = (dec.get("leakage_audit") or {}).get("status") or manifest.get("leakage_summary")
        tm = teams_manifest.get(tid) or {}
        team_decisions.append(
            {
                "agentKey": agent_key,
                "teamId": tid,
                "action": dec.get("action"),
                "ticker": ticker,
                "tickerName": names.get(str(ticker), ticker) if ticker else None,
                "targetPrice": dec.get("target_price"),
                "reasonLabel": dec.get("reason_label"),
                "reasonDetail": dec.get("reason_detail"),
                "leakageStatus": leakage,
                "fillStatus": tm.get("status"),
                "quantity": dec.get("quantity"),
                "decisionAt": dec.get("decision_at") or manifest.get("decision_at"),
            }
        )

    audit_summary = _build_audit_summary(manifest, code_audit)
    try:
        from src.trading.competition.replay.observability import (
            load_run_public_audit_summary,
            merge_public_audit_into_dashboard,
        )

        public_obs = load_run_public_audit_summary(replay_run_id)
        audit_summary = merge_public_audit_into_dashboard(audit_summary, public_obs)
    except Exception:
        pass
    reports = load_campaign_reports(cid) if cid else {"weeklyReports": {}, "monthlyReports": {}}
    final_report = reports.get("finalReport")
    campaign_manifest: dict[str, Any] = {}
    if cid:
        from src.trading.competition.replay.finalize import load_campaign_manifest

        campaign_manifest = load_campaign_manifest(cid)

    return {
        "dataSource": "replay",
        "replayRunId": replay_run_id,
        "campaignId": cid,
        "cashAmount": cash_total,
        "totalAssets": asset_total,
        "bestAgentKey": best_team_key,
        "bestAgentReturnPct": best_team_return if best_team_return > -999 else 0,
        "bestStockName": best_stock_name,
        "bestStockReturnPct": best_stock_return if best_stock_return > -999 else 0,
        "timeline": {"labels": [label_decision, label_fill], "series": timeline_series},
        "agentMeta": agent_meta,
        "stockCatalog": stock_catalog,
        "tradeHistory": trade_history,
        "notifications": [],
        "weeklyReports": reports.get("weeklyReports") or {},
        "monthlyReports": reports.get("monthlyReports") or {},
        "finalReport": final_report,
        "competitionStatus": campaign_manifest.get("competition_status"),
        "operatingDays": 1,
        "teams": {tid: agent_meta[TEAM_TO_AGENT[tid]] for tid in TEAM_IDS},
        "auditSummary": audit_summary,
        "teamDecisions": team_decisions,
        "replayMeta": {
            "tradingDate": manifest.get("trading_date"),
            "decisionAt": manifest.get("decision_at"),
            "fillDate": manifest.get("fill_date"),
            "executionMode": manifest.get("execution_mode"),
            "sessionId": manifest.get("session_id"),
            "snapshotId": manifest.get("snapshot_id"),
            "limitations": manifest.get("limitations") or [],
            "firestoreSync": manifest.get("firestore_sync"),
        },
    }


def _date_chart_label(trading_date: str) -> str:
    if len(trading_date) == 8:
        return trading_date[4:6] + "/" + trading_date[6:8]
    return trading_date or "?"


def _ensure_run_local(replay_run_id: str) -> Path | None:
    run_dir = replay_run_dir(replay_run_id)
    if run_dir.is_dir():
        return run_dir
    from src.trading.competition.replay.campaign_resume import hydrate_run_from_firestore

    if hydrate_run_from_firestore(replay_run_id):
        return run_dir
    if _prefer_firestore():
        fb = load_replay_run_firestore(replay_run_id)
        manifest = (fb or {}).get("manifest") if isinstance(fb, dict) else None
        if manifest:
            run_dir.mkdir(parents=True, exist_ok=True)
            run_dir.joinpath("manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return run_dir
    return None


def _load_run_manifest(replay_run_id: str) -> dict[str, Any]:
    run_dir = _ensure_run_local(replay_run_id)
    if not run_dir:
        return {}
    return _read_json(run_dir / "manifest.json")


def _build_campaign_timeline(
    completed_dates: dict[str, str],
) -> dict[str, Any]:
    labels = ["시작"]
    series_by_agent: dict[str, dict[str, Any]] = {}
    for tid in TEAM_IDS:
        agent_key = TEAM_TO_AGENT[tid]
        meta = TEAM_META[tid]
        series_by_agent[agent_key] = {
            "key": agent_key,
            "label": _agent_display_name(tid),
            "color": ["#4f8cff", "#34c759", "#ff9500", "#af52de"][TEAM_IDS.index(tid)],
            "data": [INITIAL_CASH_KRW],
        }

    for trading_date in sorted(completed_dates.keys()):
        rid = completed_dates[trading_date]
        run_manifest = _load_run_manifest(rid)
        labels.append(_date_chart_label(trading_date))
        accounts = run_manifest.get("accounts") or {}
        for tid in TEAM_IDS:
            agent_key = TEAM_TO_AGENT[tid]
            acc = accounts.get(tid) or {}
            total = int(acc.get("total_assets_krw") or acc.get("cash_krw") or series_by_agent[agent_key]["data"][-1])
            series_by_agent[agent_key]["data"].append(total)

    if len(labels) == 1:
        return {"labels": ["시작", "현재"], "series": list(series_by_agent.values())}

    return {"labels": labels, "series": list(series_by_agent.values())}


def build_campaign_dashboard_payload(
    campaign_id: str,
    *,
    prefer_local: bool = True,
    detail_replay_run_id: str | None = None,
) -> dict[str, Any]:
    from src.trading.competition.replay.campaign_resume import (
        campaign_exists_locally,
        hydrate_campaign_from_firestore,
        load_checkpoint,
        load_manifest,
    )

    if not campaign_exists_locally(campaign_id):
        hydrate_campaign_from_firestore(campaign_id)

    manifest = load_manifest(campaign_id)
    checkpoint = load_checkpoint(campaign_id)
    if not manifest and not checkpoint.get("accounts"):
        raise FileNotFoundError(f"campaign not found: {campaign_id}")

    completed_dates = dict(checkpoint.get("completed_dates") or manifest.get("completed_dates") or {})
    run_ids = list(checkpoint.get("run_ids") or manifest.get("run_ids") or [])
    accounts = checkpoint.get("accounts") or manifest.get("accounts") or {}
    latest_run_id = detail_replay_run_id or (run_ids[-1] if run_ids else None)

    latest_manifest = _load_run_manifest(latest_run_id) if latest_run_id else {}
    synthetic_manifest = {
        **latest_manifest,
        "campaign_id": campaign_id,
        "accounts": accounts,
        "trading_date": checkpoint.get("last_completed_date") or manifest.get("last_completed_date"),
        "decision_at": latest_manifest.get("decision_at"),
        "fill_date": latest_manifest.get("fill_date"),
        "execution_mode": manifest.get("execution_mode") or latest_manifest.get("execution_mode"),
        "leakage_summary": manifest.get("leakage_summary") or latest_manifest.get("leakage_summary"),
    }

    base_rid = latest_run_id or f"campaign_{campaign_id}"
    if latest_run_id:
        _ensure_run_local(latest_run_id)
    payload = _build_from_manifest(base_rid, synthetic_manifest, campaign_id=campaign_id)

    names: dict[str, str] = {}
    all_trades: list[dict[str, Any]] = []
    for rid in run_ids:
        run_dir = _ensure_run_local(rid)
        if not run_dir:
            continue
        snap = _read_json(run_dir / "snapshot.json")
        names.update(_ticker_name_map(snap))
        all_trades.extend(_read_jsonl(run_dir / "trades.jsonl"))

    payload["timeline"] = _build_campaign_timeline(completed_dates)
    n_done = manifest.get("days_completed")
    if n_done is None:
        n_done = len(completed_dates)
    payload["operatingDays"] = int(n_done or 0)
    payload["replayRunId"] = latest_run_id
    payload["latestReplayRunId"] = latest_run_id
    payload["campaignId"] = campaign_id
    payload["competitionStatus"] = manifest.get("competition_status")
    from src.trading.competition.replay.validation_contract import load_campaign_validation_status

    validation = load_campaign_validation_status(campaign_id)
    payload["campaignProgress"] = {
        "campaignId": campaign_id,
        "replayType": manifest.get("replay_type"),
        "startDate": manifest.get("start_date") or manifest.get("period_start"),
        "endDate": manifest.get("end_date") or manifest.get("period_end"),
        "competitionStatus": manifest.get("competition_status"),
        "needsResume": manifest.get("needs_resume"),
        "nextTradingDate": manifest.get("next_trading_date"),
        "progressLabel": manifest.get("progress_label"),
        "daysCompleted": n_done,
        "daysTotal": manifest.get("days_total"),
        "lastCompletedDate": manifest.get("last_completed_date"),
        "doNotResume": manifest.get("do_not_resume"),
        "campaignKind": manifest.get("campaign_kind"),
        "performanceStatus": validation.get("performanceStatus"),
        "formalStrategyPerformanceAllowed": validation.get("formalStrategyPerformanceAllowed"),
        "validationDashboardLabel": validation.get("dashboardLabel"),
    }
    payload["campaignValidation"] = {
        "performanceStatus": validation.get("performanceStatus"),
        "formalStrategyPerformanceAllowed": bool(validation.get("formalStrategyPerformanceAllowed")),
        "dashboardLabel": validation.get("dashboardLabel"),
        "unverifiedItems": validation.get("unverifiedItems") or [],
        "contractDocument": validation.get("contractDocument"),
    }
    if payload.get("replayMeta") is not None:
        payload["replayMeta"]["performanceStatus"] = validation.get("performanceStatus")
        payload["replayMeta"]["formalStrategyPerformanceAllowed"] = validation.get("formalStrategyPerformanceAllowed")

    trade_history: dict[str, list] = {f"agent{i}": [] for i in range(1, 5)}
    fill_date = synthetic_manifest.get("fill_date") or ""
    trade_idx = 0
    for tr in all_trades:
        if not _is_executed_trade(tr):
            continue
        tid = tr.get("team_id", "A")
        agent_key = TEAM_TO_AGENT.get(tid, "agent1")
        code = str(tr.get("ticker") or "")
        trade_history[agent_key].append(
            {
                "dayIndex": trade_idx,
                "date": (tr.get("executed_at") or tr.get("fill_at") or fill_date or "")[:10],
                "name": tr.get("name") or names.get(code) or code,
                "code": code,
                "side": "sell" if "sell" in str(tr.get("side", "")).lower() else "buy",
                "price": tr.get("fill_price_krw"),
                "qty": tr.get("quantity"),
                "pnl": tr.get("realized_pnl_krw"),
                "reason": _display_reason(tr.get("reason_label"), tr.get("reason_detail")),
                "fillDate": tr.get("fill_date") or fill_date,
                "historical": True,
            }
        )
        trade_idx += 1
    payload["tradeHistory"] = trade_history

    if detail_replay_run_id and detail_replay_run_id != latest_run_id:
        detail = build_replay_dashboard_payload(detail_replay_run_id, prefer_local=prefer_local, campaign_id=campaign_id)
        payload["teamDecisions"] = detail.get("teamDecisions") or []
        payload["auditSummary"] = detail.get("auditSummary") or payload.get("auditSummary")
        payload["replayMeta"] = detail.get("replayMeta") or payload.get("replayMeta")
        payload["replayRunId"] = detail_replay_run_id
    else:
        payload["teamDecisions"] = payload.get("teamDecisions") or []

    try:
        from src.trading.competition.replay.observability import (
            load_campaign_public_audit_summary,
            merge_public_audit_into_dashboard,
        )

        public_obs = load_campaign_public_audit_summary(campaign_id)
        if public_obs:
            payload["auditSummary"] = merge_public_audit_into_dashboard(
                payload.get("auditSummary") or {},
                public_obs,
            )
    except Exception:
        pass

    return payload


def build_replay_dashboard_payload(
    replay_run_id: str,
    *,
    prefer_local: bool = False,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    if _prefer_firestore() and not prefer_local:
        fb = load_replay_run_firestore(replay_run_id)
        if fb and fb.get("dashboard_payload"):
            payload = fb["dashboard_payload"]
            if campaign_id and not payload.get("campaignId"):
                payload["campaignId"] = campaign_id
                reps = load_campaign_reports(campaign_id)
                payload["weeklyReports"] = reps.get("weeklyReports") or {}
                payload["monthlyReports"] = reps.get("monthlyReports") or {}
                payload["finalReport"] = reps.get("finalReport")
            return payload
        if fb and fb.get("manifest"):
            return _build_from_manifest(replay_run_id, fb["manifest"], campaign_id=campaign_id)

    run_dir = replay_run_dir(replay_run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"replay run not found: {replay_run_id}")

    manifest = _read_json(run_dir / "manifest.json")
    if not manifest:
        raise FileNotFoundError(f"manifest missing: {replay_run_id}")

    return _build_from_manifest(replay_run_id, manifest, campaign_id=campaign_id or manifest.get("campaign_id"))
