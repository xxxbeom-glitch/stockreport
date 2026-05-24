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
    hit = (ck.get("completed_dates") or {}).get(trading_date)
    if hit:
        return hit
    replay_root = COMPETITION_ROOT / "replay"
    if not replay_root.is_dir():
        return None
    for manifest_path in replay_root.glob("replay_*/manifest.json"):
        m = _read_json(manifest_path)
        if m.get("campaign_id") == campaign_id and str(m.get("trading_date")) == trading_date:
            return m.get("replay_run_id") or manifest_path.parent.name
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
    if not CAMPAIGNS_ROOT.is_dir():
        return rows
    for manifest_path in sorted(CAMPAIGNS_ROOT.glob("*/manifest.json")):
        m = _read_json(manifest_path)
        status = m.get("competition_status") or "active"
        if is_terminal_status(status):
            continue
        if not m.get("needs_resume", True) and m.get("days_completed", 0) >= m.get("days_total", 0):
            continue
        rows.append(
            {
                "campaign_id": m.get("campaign_id") or manifest_path.parent.name,
                "replay_type": m.get("replay_type"),
                "progress_label": m.get("progress_label"),
                "next_trading_date": m.get("next_trading_date"),
                "days_completed": m.get("days_completed"),
                "days_total": m.get("days_total"),
                "competition_status": status,
            }
        )
    return sorted(rows, key=lambda x: str(x.get("campaign_id") or ""))
