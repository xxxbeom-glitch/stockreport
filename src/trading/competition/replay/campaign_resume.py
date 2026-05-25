"""Resumable REPLAY campaigns — chunk checkpoints, idempotent trading days."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.trading.competition.replay.reports import _week_key_from_date
from src.trading.competition.runtime import COMPETITION_ROOT

KST = ZoneInfo("Asia/Seoul")
CAMPAIGNS_ROOT = COMPETITION_ROOT / "replay" / "campaigns"
CHECKPOINT_FILE = "checkpoint.json"
TERMINAL_STATUSES = frozenset({"ended", "month_completed"})


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def camp_dir(campaign_id: str) -> Path:
    return CAMPAIGNS_ROOT / campaign_id


def is_terminal_status(status: str | None) -> bool:
    return (status or "") in TERMINAL_STATUSES


def progress_label(replay_type: str, period_start: str, completed: int, total: int) -> str:
    if replay_type == "full_audit":
        return f"전체 감사 리플레이 진행 중 · {completed} / {total} 거래일 완료"
    if replay_type == "month" and len(period_start) >= 6:
        month = int(period_start[4:6])
        return f"{month}월 리플레이 진행 중 · {completed} / {total} 거래일 완료"
    return f"REPLAY 진행 중 · {completed} / {total} 거래일 완료"


def new_campaign_id(replay_type: str, period_start: str, period_end: str) -> str:
    return f"{replay_type}_{period_start}_{period_end}_{uuid.uuid4().hex[:6]}"


def load_checkpoint(campaign_id: str) -> dict[str, Any]:
    path = camp_dir(campaign_id) / CHECKPOINT_FILE
    if path.is_file():
        return _read_json(path)
    manifest = load_manifest(campaign_id)
    completed_map = manifest.get("completed_dates") or {}
    if not completed_map and manifest.get("run_ids"):
        completed_map = _rebuild_completed_map(manifest.get("run_ids") or [])
    return {
        "campaign_id": campaign_id,
        "planned_trading_dates": manifest.get("planned_trading_dates") or manifest.get("trading_dates") or [],
        "completed_dates": completed_map,
        "run_ids": list(manifest.get("run_ids") or []),
        "accounts": manifest.get("accounts"),
        "last_completed_date": manifest.get("last_completed_date"),
    }


def load_manifest(campaign_id: str) -> dict[str, Any]:
    return _read_json(camp_dir(campaign_id) / "manifest.json")


def campaign_exists_locally(campaign_id: str) -> bool:
    return (camp_dir(campaign_id) / "manifest.json").is_file()


def hydrate_run_from_firestore(replay_run_id: str) -> bool:
    from src.trading.competition.replay.firestore_store import load_replay_run_firestore

    doc = load_replay_run_firestore(replay_run_id)
    if not doc:
        return False
    manifest = doc.get("manifest") if isinstance(doc.get("manifest"), dict) else doc
    if not manifest:
        return False
    run_dir = COMPETITION_ROOT / "replay" / replay_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "manifest.json", manifest)
    return True


def hydrate_campaign_from_firestore(campaign_id: str) -> dict[str, Any]:
    """Restore campaign manifest/checkpoint (and run manifests) from Firestore to local mirror."""
    from src.trading.competition.replay.firestore_store import load_replay_campaign_firestore

    manifest = load_replay_campaign_firestore(campaign_id)
    if not manifest:
        return {}
    manifest = dict(manifest)
    manifest["campaign_id"] = campaign_id
    manifest.setdefault("storage_source", "firestore_hydrate")

    camp_dir(campaign_id).mkdir(parents=True, exist_ok=True)
    save_manifest(campaign_id, manifest)

    completed_map = dict(manifest.get("completed_dates") or {})
    if not completed_map and manifest.get("run_ids"):
        completed_map = _rebuild_completed_map(list(manifest.get("run_ids") or []))

    for rid in manifest.get("run_ids") or []:
        local_run = COMPETITION_ROOT / "replay" / rid / "manifest.json"
        if not local_run.is_file():
            hydrate_run_from_firestore(str(rid))

    checkpoint = {
        "campaign_id": campaign_id,
        "planned_trading_dates": manifest.get("planned_trading_dates")
        or manifest.get("trading_dates")
        or [],
        "completed_dates": completed_map,
        "run_ids": list(manifest.get("run_ids") or []),
        "accounts": manifest.get("accounts"),
        "last_completed_date": manifest.get("last_completed_date"),
    }
    save_checkpoint(campaign_id, checkpoint)
    return manifest


def ensure_campaign_for_resume(
    campaign_id: str,
    *,
    allow_hydrate: bool = True,
) -> tuple[bool, dict[str, Any], str | None]:
    """
    Load campaign for resume. Returns (ok, manifest, error_code).
    Never creates a new campaign_id.
    """
    cid = (campaign_id or "").strip()
    if not cid:
        return False, {}, "campaign_id_required_for_resume"

    if campaign_exists_locally(cid):
        return True, load_manifest(cid), None

    if not allow_hydrate:
        return False, {}, "campaign_not_found_local"

    manifest = hydrate_campaign_from_firestore(cid)
    if not manifest:
        return False, {}, "campaign_not_found_firestore"

    if not campaign_exists_locally(cid):
        return False, {}, "campaign_hydrate_failed"

    return True, load_manifest(cid), None


def mark_campaign_duplicate(
    campaign_id: str,
    *,
    canonical_campaign_id: str,
    reason: str = "duplicate_restart",
) -> dict[str, Any]:
    """Tag mistaken duplicate campaign (do not delete)."""
    manifest = load_manifest(campaign_id) if campaign_exists_locally(campaign_id) else {}
    if not manifest:
        manifest = {"campaign_id": campaign_id}
    manifest.update(
        {
            "campaign_kind": "duplicate_restart",
            "do_not_resume": True,
            "canonical_campaign_id": canonical_campaign_id,
            "duplicate_reason": reason,
            "competition_status": "superseded",
            "needs_resume": False,
        }
    )
    if campaign_exists_locally(campaign_id):
        save_manifest(campaign_id, manifest)
    from src.trading.competition.replay.firestore_store import sync_replay_campaign

    sync_replay_campaign(campaign_id, manifest)
    return manifest


def save_checkpoint(campaign_id: str, checkpoint: dict[str, Any]) -> None:
    _write_json(camp_dir(campaign_id) / CHECKPOINT_FILE, checkpoint)


def save_manifest(campaign_id: str, manifest: dict[str, Any]) -> None:
    _write_json(camp_dir(campaign_id) / "manifest.json", manifest)


def _rebuild_completed_map(run_ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rid in run_ids:
        m = _read_json(COMPETITION_ROOT / "replay" / rid / "manifest.json")
        td = m.get("trading_date")
        if td:
            out[str(td)] = rid
    return out


def find_run_for_trading_date(campaign_id: str, trading_date: str) -> str | None:
    ck = load_checkpoint(campaign_id)
    dip = ck.get("day_in_progress")
    if isinstance(dip, dict) and str(dip.get("trading_date")) == trading_date:
        return None
    hit = (ck.get("completed_dates") or {}).get(trading_date)
    if hit:
        return hit
    replay_root = COMPETITION_ROOT / "replay"
    if replay_root.is_dir():
        for manifest_path in replay_root.glob("replay_*/manifest.json"):
            m = _read_json(manifest_path)
            if m.get("campaign_id") == campaign_id and str(m.get("trading_date")) == trading_date:
                return m.get("replay_run_id") or manifest_path.parent.name
    for rid in ck.get("run_ids") or []:
        doc = _read_json(COMPETITION_ROOT / "replay" / rid / "manifest.json")
        if str(doc.get("trading_date")) == trading_date:
            return rid
        from src.trading.competition.replay.firestore_store import load_replay_run_firestore

        fs = load_replay_run_firestore(str(rid))
        if fs and str((fs.get("manifest") or fs).get("trading_date")) == trading_date:
            hydrate_run_from_firestore(str(rid))
            return str(rid)
    return None


def load_accounts_from_run(replay_run_id: str) -> dict[str, dict[str, Any]] | None:
    m = _read_json(COMPETITION_ROOT / "replay" / replay_run_id / "manifest.json")
    accounts = m.get("accounts")
    if accounts:
        return copy.deepcopy(accounts)
    return None


def init_campaign_manifest(
    *,
    campaign_id: str,
    replay_type: str,
    planned_dates: list[str],
    chunk_size: int,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "replay_type": replay_type,
        "period_start": period_start,
        "period_end": period_end,
        "planned_trading_dates": planned_dates,
        "completed_trading_dates": [],
        "completed_dates": {},
        "run_ids": [],
        "trading_dates": planned_dates,
        "start_date": planned_dates[0] if planned_dates else period_start,
        "end_date": planned_dates[-1] if planned_dates else period_end,
        "chunk_size_trading_days": chunk_size,
        "competition_status": "active",
        "decisions_frozen": False,
        "needs_resume": len(planned_dates) > 0,
        "next_trading_date": planned_dates[0] if planned_dates else None,
        "days_completed": 0,
        "days_total": len(planned_dates),
        "progress_label": progress_label(replay_type, period_start, 0, len(planned_dates)),
        "slack_sent_weekly_keys": [],
        "slack_sent_monthly_keys": [],
        "affects_live_account": False,
    }


def remaining_trading_dates(campaign_id: str) -> tuple[list[str], dict[str, Any]]:
    ck = load_checkpoint(campaign_id)
    planned = list(ck.get("planned_trading_dates") or [])
    completed = set((ck.get("completed_dates") or {}).keys())
    remaining = [d for d in planned if d not in completed]
    return remaining, ck


def mark_day_completed(
    campaign_id: str,
    *,
    trading_date: str,
    replay_run_id: str,
    accounts: dict[str, dict[str, Any]],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    completed = dict(checkpoint.get("completed_dates") or {})
    completed[trading_date] = replay_run_id
    run_ids = list(checkpoint.get("run_ids") or [])
    if replay_run_id not in run_ids:
        run_ids.append(replay_run_id)
    checkpoint = {
        **checkpoint,
        "campaign_id": campaign_id,
        "completed_dates": completed,
        "run_ids": run_ids,
        "accounts": copy.deepcopy(accounts),
        "last_completed_date": trading_date,
    }
    save_checkpoint(campaign_id, checkpoint)
    return checkpoint


def sync_manifest_progress(
    campaign_id: str,
    manifest: dict[str, Any],
    checkpoint: dict[str, Any],
    *,
    planned_dates: list[str],
) -> dict[str, Any]:
    completed_dates = checkpoint.get("completed_dates") or {}
    completed_list = sorted(completed_dates.keys())
    n_done = len(completed_list)
    n_total = len(planned_dates)
    remaining, _ = remaining_trading_dates(campaign_id)
    manifest.update(
        {
            "completed_trading_dates": completed_list,
            "completed_dates": completed_dates,
            "run_ids": list(checkpoint.get("run_ids") or []),
            "accounts": checkpoint.get("accounts"),
            "last_completed_date": checkpoint.get("last_completed_date"),
            "days_completed": n_done,
            "days_total": n_total,
            "progress_label": progress_label(
                str(manifest.get("replay_type") or ""),
                str(manifest.get("period_start") or manifest.get("start_date") or ""),
                n_done,
                n_total,
            ),
            "next_trading_date": remaining[0] if remaining else None,
            "needs_resume": bool(remaining),
        }
    )
    save_manifest(campaign_id, manifest)
    return manifest


def chunk_week_key_for_slack(trading_dates: list[str]) -> str | None:
    if not trading_dates:
        return None
    return _week_key_from_date(trading_dates[-1])


def list_resumable_campaigns() -> list[dict[str, Any]]:
    """Campaigns that can be continued from Actions (needs_resume)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _append(m: dict[str, Any], *, source: str) -> None:
        if m.get("do_not_resume") or m.get("campaign_kind") == "duplicate_restart":
            return
        cid = str(m.get("campaign_id") or "")
        if not cid or cid in seen:
            return
        status = m.get("competition_status") or "active"
        if status == "superseded" or is_terminal_status(status):
            return
        if not m.get("needs_resume", True) and (m.get("days_completed") or 0) >= (m.get("days_total") or 0):
            return
        seen.add(cid)
        rows.append(
            {
                "campaign_id": cid,
                "replay_type": m.get("replay_type"),
                "progress_label": m.get("progress_label"),
                "next_trading_date": m.get("next_trading_date"),
                "days_completed": m.get("days_completed"),
                "days_total": m.get("days_total"),
                "competition_status": status,
                "source": source,
            }
        )

    if CAMPAIGNS_ROOT.is_dir():
        for manifest_path in sorted(CAMPAIGNS_ROOT.glob("*/manifest.json")):
            _append(_read_json(manifest_path), source="local")

    try:
        from src.trading.competition.constants import COLLECTION_REPLAY_CAMPAIGNS
        from src.trading.competition.storage.base import firestore_client

        client, _ = firestore_client()
        if client:
            for doc in client.collection(COLLECTION_REPLAY_CAMPAIGNS).stream():
                m = doc.to_dict() or {}
                if not m.get("campaign_id"):
                    m["campaign_id"] = doc.id
                _append(m, source="firestore")
    except Exception:
        pass

    return sorted(rows, key=lambda x: str(x.get("campaign_id") or ""))
