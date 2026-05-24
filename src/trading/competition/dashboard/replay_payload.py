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

    live_ready = leakage == "PASS" and int(code_failures or 0) == 0 and not manifest.get("reset_required_before_live")

    return {
        "leakageStatus": leakage,
        "ruleViolationCount": int(code_failures or 0),
        "committeeStatus": committee_status,
        "committeeVerdict": committee_verdict,
        "liveReady": live_ready,
        "limitations": manifest.get("limitations") or code_audit.get("limitations") or [],
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

        agent_meta[agent_key] = {
            "name": meta["display_name"],
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
                "label": meta["display_name"],
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
            block = {"avg": avg, "current": cur, "returnPct": ret_pct, "pnl": pnl}
            if code not in stock_catalog:
                stock_catalog[code] = {
                    "name": pname,
                    "agents": [],
                    "reason": pos.get("buy_reason_label") or "-",
                    "all": dict(block),
                    "7d": dict(block),
                    "14d": dict(block),
                }
            if agent_key not in stock_catalog[code]["agents"]:
                stock_catalog[code]["agents"].append(agent_key)

    for i, tr in enumerate(trades):
        tid = tr.get("team_id", "A")
        agent_key = TEAM_TO_AGENT.get(tid, "agent1")
        code = str(tr.get("ticker") or "")
        trade_history[agent_key].append(
            {
                "dayIndex": min(i, 1),
                "date": (tr.get("executed_at") or tr.get("fill_at") or fill_date or "")[:10],
                "name": tr.get("name") or names.get(code) or code,
                "code": code,
                "side": "sell" if "sell" in str(tr.get("side", "")).lower() else "buy",
                "price": tr.get("fill_price_krw"),
                "qty": tr.get("quantity"),
                "pnl": tr.get("realized_pnl_krw"),
                "reason": tr.get("reason_label") or tr.get("reason"),
                "fillDate": tr.get("fill_date") or fill_date,
                "historical": True,
            }
        )

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
    reports = load_campaign_reports(cid) if cid else {"weeklyReports": {}, "monthlyReports": {}}

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
