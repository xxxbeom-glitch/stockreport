"""Select exactly one resumable REPLAY campaign for Actions (no manual campaign_id)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.trading.competition.replay.batch_checkpoint import (
    FATAL_NO_AUTO_RETRY_ERRORS,
    should_auto_resume,
)
from src.trading.competition.replay.campaign_resume import (
    CAMPAIGNS_ROOT,
    campaign_exists_locally,
    is_terminal_status,
    load_manifest,
    remaining_trading_dates,
)
from src.trading.competition.runtime import COMPETITION_ROOT

DOCS_REPLAY_ROOT = Path(__file__).resolve().parents[4] / "docs" / "replay-data"
DOCS_CAMPAIGNS_ROOT = DOCS_REPLAY_ROOT / "campaigns"

# Errors that block auto-resume even when needs_resume is set.
FATAL_CAMPAIGN_ERRORS = frozenset(
    {
        "campaign_marked_duplicate_do_not_resume",
        "campaign_already_ended",
        "leakage_fail",
    }
)

# Recoverable when progress metadata still allows continuation.
RECOVERABLE_ERRORS = frozenset(
    {
        "data_invalid",
        "replay_day_failed",
        "data_collection_failed",
        "snapshot_failed",
        "market_data_unavailable",
        "kis_rate_limit_exceeded",
        "kis_request_budget_reached",
    }
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _camel_to_snake_manifest(meta: dict[str, Any], campaign_id: str) -> dict[str, Any]:
    """Normalize docs/replay-data meta.json fields to manifest-style keys."""
    return {
        "campaign_id": campaign_id,
        "replay_type": meta.get("replayType") or meta.get("replay_type"),
        "competition_status": meta.get("competitionStatus") or meta.get("competition_status"),
        "needs_resume": meta.get("needsResume", meta.get("needs_resume")),
        "next_trading_date": meta.get("nextTradingDate") or meta.get("next_trading_date"),
        "days_completed": meta.get("daysCompleted", meta.get("days_completed")),
        "days_total": meta.get("daysTotal", meta.get("days_total")),
        "do_not_resume": bool(meta.get("doNotResume") or meta.get("do_not_resume")),
        "campaign_kind": meta.get("campaignKind") or meta.get("campaign_kind"),
        "canonical_campaign_id": meta.get("canonicalCampaignId") or meta.get("canonical_campaign_id"),
        "start_date": meta.get("startDate") or meta.get("start_date"),
        "end_date": meta.get("endDate") or meta.get("end_date"),
        "progress_label": meta.get("progressLabel") or meta.get("progress_label"),
        "last_completed_date": meta.get("lastCompletedDate") or meta.get("last_completed_date"),
    }


# Published docs must not override live campaign state from Firestore.
EXCLUSION_KEYS = frozenset(
    {
        "do_not_resume",
        "doNotResume",
        "campaign_kind",
        "campaignKind",
        "canonical_campaign_id",
        "canonicalCampaignId",
    }
)


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _merge_record(existing: dict[str, Any], incoming: dict[str, Any], *, source: str) -> dict[str, Any]:
    """
    Merge precedence:
    1. Firestore — source of truth for operational campaign state
    2. local manifest — gap-fill / mirror when Firestore absent
    3. docs meta — duplicate exclusion flags + gap-fill only (never overrides Firestore)
    """
    out = dict(existing) if existing else {}
    sources = list(out.get("sources") or [])
    if source not in sources:
        sources.append(source)
    has_firestore = "firestore" in sources and source != "firestore"

    for key, value in incoming.items():
        if key == "sources" or value is None:
            continue
        prev = out.get(key)
        if source == "firestore":
            out[key] = value
            continue
        if source == "docs_meta":
            if key in EXCLUSION_KEYS or _is_empty(prev):
                out[key] = value
            continue
        if source == "local_manifest":
            if key in EXCLUSION_KEYS or not has_firestore or _is_empty(prev):
                out[key] = value

    out["sources"] = sources
    return out


def _load_firestore_campaigns() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    try:
        from src.trading.competition.constants import COLLECTION_REPLAY_CAMPAIGNS
        from src.trading.competition.storage.base import firestore_client

        client, _ = firestore_client()
        if not client:
            return rows
        for doc in client.collection(COLLECTION_REPLAY_CAMPAIGNS).stream():
            m = doc.to_dict() or {}
            cid = str(m.get("campaign_id") or doc.id).strip()
            if cid:
                rows[cid] = m
    except Exception:
        pass
    return rows


def gather_campaign_records() -> dict[str, dict[str, Any]]:
    """Merge Firestore (primary), local manifest, then published docs meta."""
    by_id: dict[str, dict[str, Any]] = {}

    def put(cid: str, payload: dict[str, Any], source: str) -> None:
        cid = cid.strip()
        if not cid:
            return
        payload = {**payload, "campaign_id": cid}
        by_id[cid] = _merge_record(by_id.get(cid, {}), payload, source=source)

    for cid, manifest in _load_firestore_campaigns().items():
        put(cid, manifest, "firestore")

    if CAMPAIGNS_ROOT.is_dir():
        for manifest_path in sorted(CAMPAIGNS_ROOT.glob("*/manifest.json")):
            cid = manifest_path.parent.name
            put(cid, _read_json(manifest_path), "local_manifest")

    if DOCS_CAMPAIGNS_ROOT.is_dir():
        for meta_path in sorted(DOCS_CAMPAIGNS_ROOT.glob("*/meta.json")):
            cid = meta_path.parent.name
            put(cid, _camel_to_snake_manifest(_read_json(meta_path), cid), "docs_meta")

    return by_id


def has_resume_metadata(manifest: dict[str, Any]) -> bool:
    planned = list(manifest.get("planned_trading_dates") or manifest.get("trading_dates") or [])
    if not planned:
        return False
    needs = manifest.get("needs_resume")
    if needs is None:
        needs = manifest.get("needsResume")
    next_date = manifest.get("next_trading_date") or manifest.get("nextTradingDate")
    done = int(manifest.get("days_completed") or 0)
    total = int(manifest.get("days_total") or len(planned) or 0)
    if needs is False and not next_date and done >= total > 0:
        return False
    return bool(needs or next_date or done < total)


def is_fatal_campaign_error(error: str | None, manifest: dict[str, Any]) -> bool:
    if not error:
        return False
    err = str(error).strip()
    if err in FATAL_CAMPAIGN_ERRORS:
        return True
    if err in RECOVERABLE_ERRORS:
        if manifest.get("needs_resume") or manifest.get("needsResume"):
            return False
        if manifest.get("next_trading_date") or manifest.get("nextTradingDate"):
            return False
        remaining, _ = remaining_trading_dates(str(manifest.get("campaign_id") or ""))
        return len(remaining) == 0
    return manifest.get("ok") is False and err not in RECOVERABLE_ERRORS


def resumability_exclusion_reason(manifest: dict[str, Any]) -> str | None:
    cid = str(manifest.get("campaign_id") or "").strip()
    if not cid:
        return "missing_campaign_id"

    if manifest.get("do_not_resume") or manifest.get("doNotResume"):
        return "do_not_resume"

    kind = manifest.get("campaign_kind") or manifest.get("campaignKind")
    if kind == "duplicate_restart":
        return "duplicate_restart"

    status = str(manifest.get("competition_status") or manifest.get("competitionStatus") or "active")
    if status == "superseded" or is_terminal_status(status):
        return f"terminal_status:{status}"

    if not has_resume_metadata(manifest):
        return "missing_resume_meta"

    if not should_auto_resume(manifest):
        return "not_auto_resumable"

    err = manifest.get("error")
    if is_fatal_campaign_error(str(err) if err else None, manifest):
        return f"fatal_error:{err}"

    needs = manifest.get("needs_resume")
    if needs is None:
        needs = manifest.get("needsResume", True)
    next_date = manifest.get("next_trading_date") or manifest.get("nextTradingDate")
    done = int(manifest.get("days_completed") or 0)
    total = int(manifest.get("days_total") or 0)
    if not needs and not next_date:
        if total > 0 and done >= total:
            return "already_complete"
        if not campaign_exists_locally(cid):
            remaining, _ = remaining_trading_dates(cid)
            if not remaining:
                return "already_complete"

    return None


def _candidate_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("last_completed_date") or ""),
        str(row.get("days_completed") or 0).zfill(6),
        str(row.get("campaign_id") or ""),
    )


def enrich_resumable_candidate(manifest: dict[str, Any]) -> dict[str, Any]:
    cid = str(manifest.get("campaign_id") or "")
    next_date = manifest.get("next_trading_date") or manifest.get("nextTradingDate")
    if not next_date and campaign_exists_locally(cid):
        remaining, _ = remaining_trading_dates(cid)
        if remaining:
            next_date = remaining[0]
    if not next_date:
        planned = manifest.get("planned_trading_dates") or manifest.get("trading_dates") or []
        done = set((manifest.get("completed_dates") or {}).keys())
        if not done and manifest.get("completed_trading_dates"):
            done = set(manifest.get("completed_trading_dates") or [])
        for d in planned:
            if str(d) not in done:
                next_date = str(d)
                break
    return {
        "campaign_id": cid,
        "replay_type": manifest.get("replay_type"),
        "start_date": manifest.get("start_date") or manifest.get("period_start"),
        "end_date": manifest.get("end_date") or manifest.get("period_end"),
        "next_trading_date": next_date,
        "days_completed": manifest.get("days_completed"),
        "days_total": manifest.get("days_total"),
        "progress_label": manifest.get("progress_label"),
        "competition_status": manifest.get("competition_status"),
        "sources": list(manifest.get("sources") or []),
    }


def list_auto_resumable_campaigns() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cid, manifest in gather_campaign_records().items():
        manifest = dict(manifest)
        if campaign_exists_locally(cid):
            manifest = _merge_record(manifest, load_manifest(cid), source="local_refresh")
        reason = resumability_exclusion_reason(manifest)
        if reason:
            continue
        rows.append(enrich_resumable_candidate(manifest))
    rows.sort(key=_candidate_sort_key, reverse=True)
    return rows


def select_unique_resumable_campaign() -> dict[str, Any]:
    """
    Pick exactly one campaign for resume workflow.
    Returns ok=True with campaign fields, or ok=False with error message.
    """
    candidates = list_auto_resumable_campaigns()
    if not candidates:
        return {
            "ok": False,
            "error": "No resumable campaign found",
            "candidates": [],
        }
    if len(candidates) > 1:
        return {
            "ok": False,
            "error": "Multiple resumable campaigns found. Resolve canonical campaign first.",
            "candidates": candidates,
        }
    selected = candidates[0]
    return {"ok": True, **selected, "candidates": candidates}


def format_selection_banner(result: dict[str, Any], *, chunk_days: int | None = None) -> list[str]:
    lines = ["## REPLAY resume target", ""]
    if not result.get("ok"):
        lines.append(f"**ERROR:** {result.get('error')}")
        for row in result.get("candidates") or []:
            lines.append(f"- `{row.get('campaign_id')}` (next: {row.get('next_trading_date')})")
        return lines
    lines.extend(
        [
            f"### Selected resumable campaign: `{result.get('campaign_id')}`",
            "",
            f"- **Next trading date:** `{result.get('next_trading_date')}`",
            f"- **Progress:** {result.get('days_completed')} / {result.get('days_total')} days",
            f"- **Replay type:** `{result.get('replay_type')}`",
        ]
    )
    if chunk_days is not None:
        lines.append(f"- **Chunk days:** {chunk_days}")
    return lines
