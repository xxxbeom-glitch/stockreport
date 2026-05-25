"""Publish sanitized REPLAY JSON for GitHub Pages (no LIVE, no secrets)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.trading.competition.dashboard.replay_payload import (
    build_campaign_dashboard_payload,
    build_replay_dashboard_payload,
)
from src.trading.competition.replay.firestore_store import GITHUB_PAGES_DASHBOARD_BASE, replay_report_url
from src.trading.competition.replay.observability import (
    load_campaign_public_audit_summary,
    load_run_public_audit_summary,
)
from src.trading.competition.replay.reports import load_campaign_reports
from src.trading.competition.replay.validation_contract import merge_validation_into_meta
from src.trading.competition.runtime import COMPETITION_ROOT

KST = ZoneInfo("Asia/Seoul")
REPLAY_DATA_ROOT = Path(__file__).resolve().parents[4] / "docs" / "replay-data"
LOCAL_REPLAY_ROOT = COMPETITION_ROOT / "replay"

_STRIP_KEYS = frozenset(
    {
        "firestoreSync",
        "firestore_sync",
        "evidence_ids",
        "reset_required_before_live",
        "affects_live_account",
        "profiles",
        "error_summaries",
        "models",
        "workflow",
        "role_env_keys",
        "teams",
    }
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _strip_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _STRIP_KEYS:
                continue
            if k == "replayMeta" and isinstance(v, dict):
                meta = _strip_obj(v)
                meta.pop("firestoreSync", None)
                meta.pop("limitations", None)
                out[k] = meta
                continue
            out[k] = _strip_obj(v)
        return out
    if isinstance(obj, list):
        return [_strip_obj(x) for x in obj]
    return obj


def sanitize_dashboard_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe = _strip_obj(payload)
    safe["dataSource"] = "replay"
    safe["publishedFor"] = "github_pages"
    return safe


def sanitize_report(report: dict[str, Any], *, campaign_id: str, report_type: str) -> dict[str, Any]:
    rep = _strip_obj(dict(report))
    rep.pop("save", None)
    wk = rep.get("week_key") or rep.get("month_key") or rep.get("report_key") or "final"
    rep["url"] = replay_report_url(
        campaign_id=campaign_id,
        report_key=wk if report_type != "final" else "final",
        report_type=report_type,
        replay_run_id=rep.get("last_replay_run_id"),
    )
    return rep


def publish_run_audit_summary(replay_run_id: str) -> Path | None:
    public = load_run_public_audit_summary(replay_run_id)
    if not public:
        return None
    safe = _strip_obj(public)
    path = REPLAY_DATA_ROOT / "runs" / replay_run_id / "audit_summary.json"
    _write_json(path, safe)
    return path


def publish_campaign_audit_summary(campaign_id: str) -> Path | None:
    public = load_campaign_public_audit_summary(campaign_id)
    if not public:
        return None
    safe = _strip_obj(public)
    path = REPLAY_DATA_ROOT / "campaigns" / campaign_id / "audit_summary.json"
    _write_json(path, safe)
    return path


def ensure_campaign_local(campaign_id: str) -> bool:
    from src.trading.competition.replay.campaign_resume import (
        campaign_exists_locally,
        hydrate_campaign_from_firestore,
    )

    if campaign_exists_locally(campaign_id):
        return True
    return bool(hydrate_campaign_from_firestore(campaign_id))


def publish_campaign_meta(campaign_id: str) -> Path | None:
    from src.trading.competition.replay.campaign_resume import load_manifest

    manifest = load_manifest(campaign_id)
    if not manifest:
        return None
    planned = manifest.get("planned_trading_dates") or manifest.get("trading_dates") or []
    completed = manifest.get("completed_trading_dates") or list((manifest.get("completed_dates") or {}).keys())
    n_done = manifest.get("days_completed")
    if n_done is None:
        n_done = len(completed)
    n_total = manifest.get("days_total")
    if n_total is None:
        n_total = len(planned)
    meta = {
        "campaignId": campaign_id,
        "replayType": manifest.get("replay_type"),
        "startDate": manifest.get("start_date") or manifest.get("period_start"),
        "endDate": manifest.get("end_date") or manifest.get("period_end"),
        "leakageSummary": manifest.get("leakage_summary"),
        "competitionStatus": manifest.get("competition_status"),
        "needsResume": manifest.get("needs_resume"),
        "nextTradingDate": manifest.get("next_trading_date"),
        "progressLabel": manifest.get("progress_label"),
        "daysCompleted": n_done,
        "daysTotal": n_total,
        "lastCompletedDate": manifest.get("last_completed_date"),
        "weeklyReportKeys": manifest.get("weekly_report_keys") or [],
        "monthlyReportKeys": manifest.get("monthly_report_keys") or [],
        "doNotResume": bool(manifest.get("do_not_resume")),
        "campaignKind": manifest.get("campaign_kind"),
        "canonicalCampaignId": manifest.get("canonical_campaign_id"),
        "dashboardPath": f"campaigns/{campaign_id}/dashboard.json",
        "batchStatus": manifest.get("batch_status"),
        "publicStatus": manifest.get("public_status"),
        "resumeReason": manifest.get("resume_reason"),
        "lastBatchAt": manifest.get("last_batch_at"),
        "kisRequestsUsed": manifest.get("kis_requests_used"),
        "kisRequestsBudget": manifest.get("kis_requests_budget"),
        "lastBatchKisRequests": manifest.get("last_batch_kis_requests"),
        "dayInProgress": manifest.get("day_in_progress"),
        "nextTicker": manifest.get("next_ticker"),
        "ohlcvCursorIndex": manifest.get("ohlcv_cursor_index"),
        "riskCursorIndex": manifest.get("risk_cursor_index"),
    }
    meta = merge_validation_into_meta(meta, campaign_id)
    path = REPLAY_DATA_ROOT / "campaigns" / campaign_id / "meta.json"
    _write_json(path, meta)
    return path


def publish_campaign_dashboard(campaign_id: str) -> Path | None:
    if not ensure_campaign_local(campaign_id):
        return None
    try:
        payload = build_campaign_dashboard_payload(campaign_id, prefer_local=True)
    except FileNotFoundError:
        return None
    safe = sanitize_dashboard_payload(payload)
    path = REPLAY_DATA_ROOT / "campaigns" / campaign_id / "dashboard.json"
    _write_json(path, safe)
    publish_campaign_meta(campaign_id)
    publish_campaign_audit_summary(campaign_id)
    return path


def publish_campaign_runs(campaign_id: str) -> list[str]:
    from src.trading.competition.replay.campaign_resume import load_checkpoint, load_manifest

    if not ensure_campaign_local(campaign_id):
        return []
    manifest = load_manifest(campaign_id)
    checkpoint = load_checkpoint(campaign_id)
    run_ids = list(checkpoint.get("run_ids") or manifest.get("run_ids") or [])
    completed = checkpoint.get("completed_dates") or manifest.get("completed_dates") or {}
    for rid in completed.values():
        if rid and rid not in run_ids:
            run_ids.append(str(rid))
    published: list[str] = []
    for rid in run_ids:
        if publish_run_dashboard(str(rid)):
            published.append(str(rid))
    return published


def publish_campaign_full(campaign_id: str) -> dict[str, Any]:
    """Reports + per-run dashboards + campaign cumulative dashboard."""
    if not ensure_campaign_local(campaign_id):
        return {"ok": False, "error": "campaign_not_found", "campaign_id": campaign_id}
    runs = publish_campaign_runs(campaign_id)
    dashboard = publish_campaign_dashboard(campaign_id)
    reports = publish_campaign_reports(campaign_id)
    return {
        "ok": bool(dashboard),
        "campaign_id": campaign_id,
        "published_runs": runs,
        "campaign_dashboard": str(dashboard) if dashboard else None,
        "reports": reports,
    }


def publish_run_dashboard(replay_run_id: str) -> Path | None:
    payload: dict[str, Any] | None = None
    try:
        payload = build_replay_dashboard_payload(replay_run_id, prefer_local=True)
    except FileNotFoundError:
        payload = None
    if payload is None:
        from src.trading.competition.dashboard.replay_payload import _build_from_manifest, _load_run_manifest

        manifest = _load_run_manifest(replay_run_id)
        if not manifest:
            return None
        payload = _build_from_manifest(replay_run_id, manifest, campaign_id=manifest.get("campaign_id"))
    safe = sanitize_dashboard_payload(payload)
    path = REPLAY_DATA_ROOT / "runs" / replay_run_id / "dashboard.json"
    _write_json(path, safe)
    publish_run_audit_summary(replay_run_id)
    return path


def publish_campaign_reports(campaign_id: str) -> dict[str, list[str]]:
    reports = load_campaign_reports(campaign_id)
    written: dict[str, list[str]] = {"weekly": [], "monthly": [], "final": []}

    for wk, rep in (reports.get("weeklyReports") or {}).items():
        safe = sanitize_report(rep, campaign_id=campaign_id, report_type="weekly")
        rel = f"campaigns/{campaign_id}/weekly/{wk}.json"
        _write_json(REPLAY_DATA_ROOT / rel, safe)
        written["weekly"].append(wk)

    for mk, rep in (reports.get("monthlyReports") or {}).items():
        safe = sanitize_report(rep, campaign_id=campaign_id, report_type="monthly")
        rel = f"campaigns/{campaign_id}/monthly/{mk}.json"
        _write_json(REPLAY_DATA_ROOT / rel, safe)
        written["monthly"].append(mk)

    final = reports.get("finalReport")
    if final:
        safe = sanitize_report(final, campaign_id=campaign_id, report_type="final")
        _write_json(REPLAY_DATA_ROOT / f"campaigns/{campaign_id}/final.json", safe)
        written["final"].append("final")

    publish_campaign_audit_summary(campaign_id)
    return written


def _campaign_meta(campaign_id: str) -> dict[str, Any]:
    published_meta = REPLAY_DATA_ROOT / "campaigns" / campaign_id / "meta.json"
    if published_meta.is_file():
        return _read_json(published_meta)
    manifest_path = LOCAL_REPLAY_ROOT / "campaigns" / campaign_id / "manifest.json"
    m = _read_json(manifest_path)
    planned = m.get("planned_trading_dates") or m.get("trading_dates") or []
    completed = m.get("completed_trading_dates") or list((m.get("completed_dates") or {}).keys())
    n_done = m.get("days_completed")
    if n_done is None:
        n_done = len(completed)
    n_total = m.get("days_total")
    if n_total is None:
        n_total = len(planned)
    return {
        "campaignId": campaign_id,
        "replayType": m.get("replay_type"),
        "startDate": m.get("start_date"),
        "endDate": m.get("end_date"),
        "leakageSummary": m.get("leakage_summary"),
        "competitionStatus": m.get("competition_status"),
        "needsResume": m.get("needs_resume"),
        "nextTradingDate": m.get("next_trading_date"),
        "progressLabel": m.get("progress_label"),
        "daysCompleted": n_done,
        "daysTotal": n_total,
        "lastCompletedDate": m.get("last_completed_date"),
        "weeklyReportKeys": m.get("weekly_report_keys") or [],
        "monthlyReportKeys": m.get("monthly_report_keys") or [],
        "doNotResume": bool(m.get("do_not_resume")),
        "campaignKind": m.get("campaign_kind"),
        "canonicalCampaignId": m.get("canonical_campaign_id"),
        "dashboardPath": f"campaigns/{campaign_id}/dashboard.json",
    }


def rebuild_index() -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    runs_dir = REPLAY_DATA_ROOT / "runs"
    if runs_dir.is_dir():
        for run_path in sorted(runs_dir.glob("*/dashboard.json")):
            run_id = run_path.parent.name
            dash = _read_json(run_path)
            meta = dash.get("replayMeta") or {}
            runs.append(
                {
                    "replayRunId": run_id,
                    "tradingDate": meta.get("tradingDate"),
                    "campaignId": dash.get("campaignId"),
                    "leakageSummary": (dash.get("auditSummary") or {}).get("leakageStatus"),
                    "dashboardPath": f"runs/{run_id}/dashboard.json",
                }
            )

    campaigns: dict[str, Any] = {}
    camps_dir = REPLAY_DATA_ROOT / "campaigns"
    if camps_dir.is_dir():
        for camp_dir in sorted(camps_dir.iterdir()):
            if not camp_dir.is_dir():
                continue
            cid = camp_dir.name
            meta = _campaign_meta(cid)
            if meta.get("doNotResume") or meta.get("campaignKind") == "duplicate_restart":
                continue
            entry: dict[str, Any] = {
                **meta,
                "weekly": sorted(p.stem for p in (camp_dir / "weekly").glob("*.json")),
                "monthly": sorted(p.stem for p in (camp_dir / "monthly").glob("*.json")),
                "hasFinal": (camp_dir / "final.json").is_file(),
                "hasAuditSummary": (camp_dir / "audit_summary.json").is_file(),
                "hasCampaignDashboard": (camp_dir / "dashboard.json").is_file(),
            }
            campaigns[cid] = entry

    index = {
        "updatedAt": datetime.now(KST).isoformat(),
        "dashboardBaseUrl": GITHUB_PAGES_DASHBOARD_BASE,
        "dashboardPath": "/template/dashboard_desktop/",
        "dataRoot": "/docs/replay-data",
        "runs": runs,
        "campaigns": campaigns,
    }
    _write_json(REPLAY_DATA_ROOT / "index.json", index)
    return index


def rebuild_pages_mirror(*, clean: bool = False) -> dict[str, Any]:
    """Rebuild docs/replay-data from data/competition/replay (idempotent)."""
    if clean and REPLAY_DATA_ROOT.is_dir():
        shutil.rmtree(REPLAY_DATA_ROOT)
    REPLAY_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    (REPLAY_DATA_ROOT / ".gitkeep").write_text("", encoding="utf-8")

    published_runs = 0
    for manifest_path in sorted(LOCAL_REPLAY_ROOT.glob("*/manifest.json")):
        if manifest_path.parent.name == "campaigns":
            continue
        m = _read_json(manifest_path)
        rid = m.get("replay_run_id") or manifest_path.parent.name
        if publish_run_dashboard(rid):
            published_runs += 1

    published_campaigns = 0
    camps_root = LOCAL_REPLAY_ROOT / "campaigns"
    if camps_root.is_dir():
        for camp_manifest in sorted(camps_root.glob("*/manifest.json")):
            cid = camp_manifest.parent.name
            manifest = _read_json(camp_manifest)
            if manifest.get("do_not_resume") or manifest.get("campaign_kind") == "duplicate_restart":
                continue
            publish_campaign_full(cid)
            published_campaigns += 1

    index = rebuild_index()
    return {
        "ok": True,
        "published_runs": published_runs,
        "published_campaigns": published_campaigns,
        "index": index,
    }
