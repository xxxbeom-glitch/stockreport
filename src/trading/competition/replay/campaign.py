"""Multi-day REPLAY campaign orchestration."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from src.trading.competition.replay.calendar import resolve_replay_dates
from src.trading.competition.replay.firestore_store import sync_replay_campaign
from src.trading.competition.replay.reports import (
    build_replay_monthly_reports,
    build_replay_weekly_reports,
    save_campaign_reports,
)
from src.trading.competition.replay.runner import run_replay_single_day
from src.trading.competition.replay.slack_reports import (
    send_fatal_replay_error,
    send_monthly_report_link,
    send_weekly_report_link,
)
from src.trading.competition.runtime import COMPETITION_ROOT

CAMPAIGNS_ROOT = COMPETITION_ROOT / "replay" / "campaigns"


def run_replay_campaign(
    replay_type: str,
    start_date: str,
    end_date: str | None = None,
    *,
    force_mock: bool = False,
    send_slack_reports: bool = False,
    slack_dry_run: bool = False,
    run_audit_ai: bool = False,
) -> dict[str, Any]:
    os.environ["COMPETITION_EXECUTION_MODE"] = (
        "replay_audit" if replay_type == "full_audit" else "replay_smoke"
    )
    os.environ.setdefault("COMPETITION_LIVE_SCHEDULE_DISABLED", "1")

    dates = resolve_replay_dates(replay_type, start_date, end_date)
    if not dates:
        err = {"ok": False, "error": "no_trading_dates", "replay_type": replay_type}
        if send_slack_reports:
            err["slack"] = send_fatal_replay_error("거래일을 찾을 수 없습니다", dry_run=slack_dry_run)
        return err

    max_days = int(os.getenv("REPLAY_MAX_DAYS", "0") or "0")
    if max_days > 0:
        dates = dates[:max_days]

    campaign_id = f"{replay_type}_{dates[0]}_{dates[-1]}_{uuid.uuid4().hex[:6]}"
    camp_dir = CAMPAIGNS_ROOT / campaign_id
    camp_dir.mkdir(parents=True, exist_ok=True)

    accounts: dict[str, dict[str, Any]] | None = None
    run_ids: list[str] = []
    leakage_statuses: list[str] = []

    for trading_date in dates:
        day_result = run_replay_single_day(
            trading_date,
            accounts=accounts,
            campaign_id=campaign_id,
            force_mock=force_mock,
            run_audit_ai=run_audit_ai and trading_date == dates[-1],
            sync_firestore=True,
        )
        if not day_result.get("ok") and day_result.get("error"):
            manifest = {
                "ok": False,
                "campaign_id": campaign_id,
                "replay_type": replay_type,
                "error": day_result.get("error"),
                "run_ids": run_ids,
            }
            (camp_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if send_slack_reports:
                manifest["slack"] = send_fatal_replay_error(
                    f"REPLAY 중단: {day_result.get('error')}", dry_run=slack_dry_run
                )
            return manifest

        accounts = day_result.get("accounts")
        run_ids.append(day_result["replay_run_id"])
        leakage_statuses.append(str(day_result.get("leakage_summary") or ""))

    leakage_summary = "PASS" if all(s == "PASS" for s in leakage_statuses if s) else "LIMITED"
    if "FAIL" in leakage_statuses:
        leakage_summary = "FAIL"

    weekly = build_replay_weekly_reports(campaign_id, run_ids, leakage_summary=leakage_summary)
    monthly = build_replay_monthly_reports(campaign_id, run_ids, leakage_summary=leakage_summary)
    report_sync = save_campaign_reports(campaign_id, weekly, monthly)

    slack_out: dict[str, Any] = {"weekly": [], "monthly": []}
    if send_slack_reports:
        for rep in weekly:
            slack_out["weekly"].append(
                send_weekly_report_link(rep, campaign_id=campaign_id, dry_run=slack_dry_run)
            )
        for rep in monthly:
            slack_out["monthly"].append(
                send_monthly_report_link(rep, campaign_id=campaign_id, dry_run=slack_dry_run)
            )

    manifest = {
        "ok": leakage_summary != "FAIL",
        "campaign_id": campaign_id,
        "replay_type": replay_type,
        "start_date": dates[0],
        "end_date": dates[-1],
        "trading_dates": dates,
        "run_ids": run_ids,
        "leakage_summary": leakage_summary,
        "weekly_report_keys": [r["week_key"] for r in weekly],
        "monthly_report_keys": [r["month_key"] for r in monthly],
        "affects_live_account": False,
        "execution_mode": os.environ.get("COMPETITION_EXECUTION_MODE"),
        "report_sync": report_sync,
        "slack": slack_out if send_slack_reports else {"skipped": True},
    }
    (camp_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    sync_replay_campaign(campaign_id, manifest)
    return manifest
