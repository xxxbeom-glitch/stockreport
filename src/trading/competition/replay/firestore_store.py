"""Firestore persistence for REPLAY — isolated from LIVE competition collections."""

from __future__ import annotations

import os
from typing import Any

from src.trading.competition.constants import (
    COLLECTION_REPLAY_CAMPAIGNS,
    COLLECTION_REPLAY_FINAL_REPORTS,
    COLLECTION_REPLAY_MONTHLY_REPORTS,
    COLLECTION_REPLAY_RUNS,
    COLLECTION_REPLAY_WEEKLY_REPORTS,
)
from src.trading.competition.storage.base import firestore_client, persist_result


def _set_doc(collection: str, doc_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    client, status = firestore_client()
    if not client:
        return persist_result(local_ok=True, firestore_ok=False, firestore_error=status.get("error", ""))
    try:
        client.collection(collection).document(doc_id).set(payload, merge=True)
        return persist_result(local_ok=True, firestore_ok=True)
    except Exception as exc:
        return persist_result(
            local_ok=True,
            firestore_ok=False,
            firestore_error=f"{type(exc).__name__}:{exc}",
        )


def sync_replay_run(
    replay_run_id: str,
    *,
    manifest: dict[str, Any],
    dashboard_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc = {
        "replay_run_id": replay_run_id,
        "execution_mode": manifest.get("execution_mode"),
        "trading_date": manifest.get("trading_date"),
        "campaign_id": manifest.get("campaign_id"),
        "leakage_summary": manifest.get("leakage_summary"),
        "manifest": manifest,
        "affects_live_account": False,
    }
    if dashboard_payload is not None:
        doc["dashboard_payload"] = dashboard_payload
    return _set_doc(COLLECTION_REPLAY_RUNS, replay_run_id, doc)


def sync_replay_campaign(campaign_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    return _set_doc(COLLECTION_REPLAY_CAMPAIGNS, campaign_id, manifest)


def sync_replay_weekly_report(report_id: str, report: dict[str, Any]) -> dict[str, Any]:
    return _set_doc(COLLECTION_REPLAY_WEEKLY_REPORTS, report_id, report)


def sync_replay_monthly_report(report_id: str, report: dict[str, Any]) -> dict[str, Any]:
    return _set_doc(COLLECTION_REPLAY_MONTHLY_REPORTS, report_id, report)


def sync_replay_final_report(report_id: str, report: dict[str, Any]) -> dict[str, Any]:
    return _set_doc(COLLECTION_REPLAY_FINAL_REPORTS, report_id, report)


def load_replay_final_report_firestore(report_id: str) -> dict[str, Any] | None:
    client, _ = firestore_client()
    if not client:
        return None
    try:
        snap = client.collection(COLLECTION_REPLAY_FINAL_REPORTS).document(report_id).get()
        return snap.to_dict() if snap.exists else None
    except Exception:
        return None


def load_replay_run_firestore(replay_run_id: str) -> dict[str, Any] | None:
    client, status = firestore_client()
    if not client:
        return None
    try:
        snap = client.collection(COLLECTION_REPLAY_RUNS).document(replay_run_id).get()
        if snap.exists:
            data = snap.to_dict() or {}
            data["_firestore_ok"] = True
            return data
    except Exception:
        return None
    return None


def list_replay_runs_firestore(limit: int = 50) -> list[dict[str, Any]]:
    client, _ = firestore_client()
    if not client:
        return []
    try:
        q = client.collection(COLLECTION_REPLAY_RUNS).order_by("trading_date", direction="DESCENDING").limit(limit)
        return [doc.to_dict() or {} for doc in q.stream()]
    except Exception:
        try:
            return [doc.to_dict() or {} for doc in client.collection(COLLECTION_REPLAY_RUNS).limit(limit).stream()]
        except Exception:
            return []


def load_replay_weekly_report_firestore(report_id: str) -> dict[str, Any] | None:
    client, _ = firestore_client()
    if not client:
        return None
    try:
        snap = client.collection(COLLECTION_REPLAY_WEEKLY_REPORTS).document(report_id).get()
        return snap.to_dict() if snap.exists else None
    except Exception:
        return None


def load_replay_monthly_report_firestore(report_id: str) -> dict[str, Any] | None:
    client, _ = firestore_client()
    if not client:
        return None
    try:
        snap = client.collection(COLLECTION_REPLAY_MONTHLY_REPORTS).document(report_id).get()
        return snap.to_dict() if snap.exists else None
    except Exception:
        return None


def list_replay_weekly_reports_firestore(campaign_id: str | None = None) -> list[dict[str, Any]]:
    client, _ = firestore_client()
    if not client:
        return []
    try:
        col = client.collection(COLLECTION_REPLAY_WEEKLY_REPORTS)
        if campaign_id:
            docs = col.where("campaign_id", "==", campaign_id).stream()
        else:
            docs = col.limit(100).stream()
        return [d.to_dict() or {} for d in docs]
    except Exception:
        return []


def list_replay_monthly_reports_firestore(campaign_id: str | None = None) -> list[dict[str, Any]]:
    client, _ = firestore_client()
    if not client:
        return []
    try:
        col = client.collection(COLLECTION_REPLAY_MONTHLY_REPORTS)
        if campaign_id:
            docs = col.where("campaign_id", "==", campaign_id).stream()
        else:
            docs = col.limit(50).stream()
        return [d.to_dict() or {} for d in docs]
    except Exception:
        return []


def replay_dashboard_base_url() -> str:
    return (
        os.getenv("COMPETITION_DASHBOARD_BASE_URL", "").strip()
        or os.getenv("DASHBOARD_BASE_URL", "").strip()
        or "http://127.0.0.1:8080"
    ).rstrip("/")


def replay_report_url(
    *,
    campaign_id: str,
    report_key: str,
    report_type: str = "weekly",
    replay_run_id: str | None = None,
) -> str:
    base = replay_dashboard_base_url()
    params = [
        "mode=replay",
        f"campaign={campaign_id}",
        f"report={report_key}",
        f"reportType={report_type}",
    ]
    if replay_run_id:
        params.append(f"replay_run_id={replay_run_id}")
    return f"{base}/template/dashboard_desktop/?{'&'.join(params)}"
