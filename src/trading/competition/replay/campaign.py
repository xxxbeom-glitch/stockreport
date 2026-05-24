"""Multi-day REPLAY campaign orchestration (resumable chunks)."""

from __future__ import annotations

import os
from typing import Any

from src.trading.competition.replay.calendar import resolve_replay_dates_with_meta
from src.trading.competition.replay.campaign_resume import (
    TERMINAL_STATUSES,
    camp_dir,
    chunk_week_key_for_slack,
    ensure_campaign_for_resume,
    find_run_for_trading_date,
    init_campaign_manifest,
    is_terminal_status,
    load_accounts_from_run,
    load_checkpoint,
    load_manifest,
    mark_day_completed,
    new_campaign_id,
    remaining_trading_dates,
    save_checkpoint,
    save_manifest,
    sync_manifest_progress,
)
from src.trading.competition.replay.firestore_store import sync_replay_campaign
from src.trading.competition.replay.finalize import finalize_full_audit_campaign, is_campaign_ended
from src.trading.competition.replay.final_report import build_replay_final_report, save_final_report
from src.trading.competition.replay.period import (
    FULL_AUDIT_END,
    FULL_AUDIT_START,
    is_full_audit_complete,
)
from src.trading.competition.replay.reports import (
    _month_key_from_date,
    build_replay_monthly_reports,
    build_replay_weekly_reports,
    save_campaign_reports,
)
from src.trading.competition.replay.runner import run_replay_single_day
from src.trading.competition.replay.batch_checkpoint import (
    FATAL_NO_AUTO_RETRY_ERRORS,
    apply_fatal_stop,
    apply_rate_limit_pause,
    apply_request_budget_checkpoint,
    attach_batch_progress,
    is_budget_checkpoint_result,
    is_rate_limit_pause_result,
)
from src.trading.competition.replay.slack_reports import (
    send_fatal_replay_error,
    send_final_report_link,
    send_monthly_report_link,
    send_rate_limit_pause_notification,
    send_weekly_report_link,
)


def _sync_campaign_batch(
    campaign_id: str,
    manifest: dict[str, Any],
    checkpoint: dict[str, Any],
    *,
    planned_dates: list[str],
) -> dict[str, Any]:
    manifest = sync_manifest_progress(campaign_id, manifest, checkpoint, planned_dates=planned_dates)
    manifest = attach_batch_progress(manifest)
    sync_replay_campaign(campaign_id, manifest)
    return manifest


def run_replay_campaign(
    replay_type: str,
    start_date: str,
    end_date: str | None = None,
    *,
    force_mock: bool = False,
    send_slack_reports: bool = True,
    slack_dry_run: bool = False,
    run_audit_ai: bool = False,
    campaign_id: str | None = None,
    resume_existing_campaign: bool = False,
    chunk_size_trading_days: int = 5,
) -> dict[str, Any]:
    os.environ["COMPETITION_EXECUTION_MODE"] = (
        "replay_audit" if replay_type == "full_audit" else "replay_smoke"
    )
    os.environ.setdefault("COMPETITION_LIVE_SCHEDULE_DISABLED", "1")

    period_start = start_date
    period_end = end_date or start_date
    if replay_type == "full_audit":
        period_start = FULL_AUDIT_START
        period_end = FULL_AUDIT_END
        start_date = FULL_AUDIT_START
        end_date = FULL_AUDIT_END

    chunk_size = chunk_size_trading_days
    env_cap = int(os.getenv("REPLAY_MAX_DAYS", "0") or "0")
    if env_cap > 0:
        chunk_size = min(chunk_size, env_cap)

    requested_campaign_id = (campaign_id or "").strip()

    if resume_existing_campaign:
        if not requested_campaign_id:
            return {"ok": False, "error": "campaign_id_required_for_resume"}
        ok_resume, manifest, resume_err = ensure_campaign_for_resume(requested_campaign_id)
        if not ok_resume:
            return {
                "ok": False,
                "error": resume_err or "campaign_not_found",
                "campaign_id": requested_campaign_id,
                "resume_requested": True,
                "hint": "Firestore/local에 checkpoint가 없으면 새 campaign을 만들지 않고 중단합니다.",
            }
        campaign_id = requested_campaign_id
        if str(manifest.get("campaign_id") or campaign_id) != requested_campaign_id:
            return {
                "ok": False,
                "error": "resume_campaign_id_mismatch",
                "requested_campaign_id": requested_campaign_id,
                "loaded_campaign_id": manifest.get("campaign_id"),
            }
        if manifest.get("do_not_resume") or manifest.get("campaign_kind") == "duplicate_restart":
            return {
                "ok": False,
                "error": "campaign_marked_duplicate_do_not_resume",
                "campaign_id": campaign_id,
                "canonical_campaign_id": manifest.get("canonical_campaign_id"),
            }
        if is_terminal_status(manifest.get("competition_status")):
            return {
                "ok": True,
                "campaign_id": campaign_id,
                "competition_status": manifest.get("competition_status"),
                "already_completed": True,
                "progress_label": manifest.get("progress_label"),
                "needs_resume": False,
            }
        planned_dates = list(
            manifest.get("planned_trading_dates") or manifest.get("trading_dates") or []
        )
        replay_type = str(manifest.get("replay_type") or replay_type)
        manifest["resume_mode"] = True
    else:
        if requested_campaign_id:
            return {
                "ok": False,
                "error": "campaign_id_only_with_resume",
                "hint": "Set resume_existing_campaign=true to continue",
            }
        dates, date_meta = resolve_replay_dates_with_meta(replay_type, start_date, end_date)
        if not dates:
            detail = date_meta.get("error") or "; ".join(date_meta.get("errors") or []) or "unknown"
            err = {
                "ok": False,
                "error": "data_collection_failed",
                "sub_error": "no_trading_dates",
                "replay_type": replay_type,
                "date_resolution": date_meta,
            }
            if send_slack_reports:
                err["slack"] = send_fatal_replay_error(
                    f"REPLAY 거래일 조회 실패 (KIS·pykrx 모두 실패): {detail}",
                    dry_run=slack_dry_run,
                )
            return err
        planned_dates = dates
        period_start = planned_dates[0]
        period_end = planned_dates[-1]
        campaign_id = new_campaign_id(replay_type, period_start, period_end)
        if resume_existing_campaign:
            return {
                "ok": False,
                "error": "resume_must_not_create_new_campaign",
                "requested_campaign_id": requested_campaign_id,
                "created_campaign_id": campaign_id,
            }
        camp_dir(campaign_id).mkdir(parents=True, exist_ok=True)
        manifest = init_campaign_manifest(
            campaign_id=campaign_id,
            replay_type=replay_type,
            planned_dates=planned_dates,
            chunk_size=chunk_size,
            period_start=period_start,
            period_end=period_end,
        )
        save_checkpoint(
            campaign_id,
            {
                "campaign_id": campaign_id,
                "planned_trading_dates": planned_dates,
                "completed_dates": {},
                "run_ids": [],
                "accounts": None,
            },
        )
        save_manifest(campaign_id, manifest)
        sync_replay_campaign(campaign_id, manifest)

    remaining, checkpoint = remaining_trading_dates(campaign_id)
    if not remaining:
        manifest = load_manifest(campaign_id)
        return {
            **manifest,
            "ok": True,
            "chunk_processed_dates": [],
            "already_completed": is_terminal_status(manifest.get("competition_status")),
        }

    chunk_dates = remaining[:chunk_size]
    accounts = checkpoint.get("accounts")
    if accounts:
        accounts = dict(accounts)
    run_ids = list(checkpoint.get("run_ids") or [])
    leakage_statuses: list[str] = []
    chunk_new_dates: list[str] = []
    last_day_result: dict[str, Any] | None = None

    from data.kis_client import reset_kis_rate_limit

    reset_kis_rate_limit()

    manifest = load_manifest(campaign_id)
    if manifest.get("competition_status") in (
        "checkpoint_waiting_resume",
        "kis_rate_limit_paused",
    ):
        manifest["competition_status"] = "active"
        save_manifest(campaign_id, manifest)

    for trading_date in chunk_dates:
        from data.kis_rate_limit import is_kis_request_budget_reached

        if is_kis_request_budget_reached():
            manifest = load_manifest(campaign_id)
            manifest = apply_request_budget_checkpoint(
                manifest,
                campaign_id=campaign_id,
                chunk_processed_dates=chunk_new_dates,
            )
            manifest = _sync_campaign_batch(
                campaign_id, manifest, checkpoint, planned_dates=planned_dates
            )
            return manifest

        if is_campaign_ended(campaign_id):
            return {
                "ok": False,
                "campaign_id": campaign_id,
                "error": "campaign_already_ended",
                "competition_status": load_manifest(campaign_id).get("competition_status"),
            }

        existing_run = find_run_for_trading_date(campaign_id, trading_date)
        if existing_run:
            loaded = load_accounts_from_run(existing_run)
            if loaded:
                accounts = loaded
            if existing_run not in run_ids:
                run_ids.append(existing_run)
            checkpoint = mark_day_completed(
                campaign_id,
                trading_date=trading_date,
                replay_run_id=existing_run,
                accounts=accounts or {},
                checkpoint=checkpoint,
            )
            continue

        day_result = run_replay_single_day(
            trading_date,
            accounts=accounts,
            campaign_id=campaign_id,
            force_mock=force_mock,
            run_audit_ai=run_audit_ai and trading_date == planned_dates[-1],
            sync_firestore=True,
        )
        if not day_result.get("ok"):
            err = str(day_result.get("error") or "replay_day_failed")
            manifest = load_manifest(campaign_id)

            if is_budget_checkpoint_result(day_result):
                manifest = apply_request_budget_checkpoint(
                    manifest,
                    campaign_id=campaign_id,
                    chunk_processed_dates=chunk_new_dates,
                )
                manifest = _sync_campaign_batch(
                    campaign_id, manifest, checkpoint, planned_dates=planned_dates
                )
                return manifest

            if is_rate_limit_pause_result(day_result):
                manifest = apply_rate_limit_pause(
                    manifest,
                    campaign_id=campaign_id,
                    failed_trading_date=trading_date,
                    chunk_processed_dates=chunk_new_dates,
                    day_result=day_result,
                )
                manifest = _sync_campaign_batch(
                    campaign_id, manifest, checkpoint, planned_dates=planned_dates
                )
                if send_slack_reports and not manifest.get("slack_sent_rate_limit_pause"):
                    manifest["slack"] = send_rate_limit_pause_notification(
                        campaign_id,
                        next_trading_date=trading_date,
                        dry_run=slack_dry_run,
                    )
                    manifest["slack_sent_rate_limit_pause"] = bool(
                        (manifest.get("slack") or {}).get("ok")
                    )
                else:
                    manifest["slack"] = {"skipped": True}
                sync_replay_campaign(campaign_id, manifest)
                return manifest

            if err in FATAL_NO_AUTO_RETRY_ERRORS or err.startswith("kis_auth"):
                manifest = apply_fatal_stop(
                    manifest,
                    campaign_id=campaign_id,
                    error=err,
                    failed_trading_date=trading_date,
                    chunk_processed_dates=chunk_new_dates,
                )
                manifest = _sync_campaign_batch(
                    campaign_id, manifest, checkpoint, planned_dates=planned_dates
                )
                if send_slack_reports:
                    manifest["slack"] = send_fatal_replay_error(
                        f"REPLAY 중단 ({trading_date}): {err} — 자동 재개 안 함",
                        dry_run=slack_dry_run,
                    )
                return manifest

            manifest.update(
                {
                    "ok": False,
                    "error": err,
                    "data_status": (day_result.get("data_validity") or {}).get("data_status")
                    or day_result.get("error"),
                    "failed_trading_date": trading_date,
                    "chunk_processed_dates": chunk_new_dates,
                }
            )
            manifest = _sync_campaign_batch(
                campaign_id, manifest, checkpoint, planned_dates=planned_dates
            )
            if send_slack_reports:
                manifest["slack"] = send_fatal_replay_error(
                    f"REPLAY chunk 중단 ({trading_date}): {err}",
                    dry_run=slack_dry_run,
                )
            return manifest

        accounts = day_result.get("accounts")
        rid = day_result["replay_run_id"]
        checkpoint = mark_day_completed(
            campaign_id,
            trading_date=trading_date,
            replay_run_id=rid,
            accounts=accounts or {},
            checkpoint=checkpoint,
        )
        run_ids = list(checkpoint.get("run_ids") or [])
        leakage_statuses.append(str(day_result.get("leakage_summary") or ""))
        chunk_new_dates.append(trading_date)
        last_day_result = day_result

    manifest = load_manifest(campaign_id)
    manifest = sync_manifest_progress(
        campaign_id, manifest, checkpoint, planned_dates=planned_dates
    )
    manifest = attach_batch_progress(manifest)

    all_leakage = list(manifest.get("leakage_statuses") or [])
    all_leakage.extend(leakage_statuses)
    leakage_summary = "PASS" if all(s == "PASS" for s in all_leakage if s) else "LIMITED"
    if "FAIL" in all_leakage:
        leakage_summary = "FAIL"
    manifest["leakage_summary"] = leakage_summary
    manifest["leakage_statuses"] = all_leakage

    weekly = build_replay_weekly_reports(campaign_id, run_ids, leakage_summary=leakage_summary)
    monthly = build_replay_monthly_reports(campaign_id, run_ids, leakage_summary=leakage_summary)
    report_sync = save_campaign_reports(campaign_id, weekly, monthly)
    manifest["weekly_report_keys"] = [r["week_key"] for r in weekly]
    manifest["monthly_report_keys"] = [r["month_key"] for r in monthly]
    manifest["report_sync"] = report_sync

    remaining_after, _ = remaining_trading_dates(campaign_id)
    campaign_complete = len(remaining_after) == 0

    slack_out: dict[str, Any] = {"weekly": None, "monthly": None, "final": None}
    sent_weekly = list(manifest.get("slack_sent_weekly_keys") or [])
    sent_monthly = list(manifest.get("slack_sent_monthly_keys") or [])

    if send_slack_reports and chunk_new_dates:
        wk = chunk_week_key_for_slack(chunk_new_dates)
        if wk and wk not in sent_weekly:
            rep = next((r for r in weekly if r.get("week_key") == wk), None)
            if rep:
                slack_out["weekly"] = send_weekly_report_link(
                    rep, campaign_id=campaign_id, dry_run=slack_dry_run
                )
                sent_weekly.append(wk)

    final_report: dict[str, Any] | None = None
    full_audit_ended = False

    if campaign_complete:
        last_date = planned_dates[-1]
        if replay_type == "full_audit" and is_full_audit_complete(last_date):
            full_audit_ended = True
            ended_manifest = finalize_full_audit_campaign(
                campaign_id,
                accounts or {},
                last_trading_date=last_date,
                run_ids=run_ids,
            )
            accounts = ended_manifest.get("final_accounts") or accounts
            manifest.update(ended_manifest)
            final_report = build_replay_final_report(
                campaign_id,
                run_ids,
                accounts or {},
                last_trading_date=last_date,
                leakage_summary=leakage_summary,
                last_manifest=last_day_result,
            )
            final_report["save"] = save_final_report(campaign_id, final_report)
            manifest["final_report_id"] = final_report.get("report_id")
            manifest["competition_status"] = "ended"
            manifest["decisions_frozen"] = True
            if send_slack_reports and final_report:
                slack_out["final"] = send_final_report_link(
                    final_report, campaign_id=campaign_id, dry_run=slack_dry_run
                )
        else:
            manifest["competition_status"] = "month_completed"
            manifest["decisions_frozen"] = True
            mk = _month_key_from_date(planned_dates[-1])
            if send_slack_reports and mk not in sent_monthly:
                rep = next((r for r in monthly if r.get("month_key") == mk), None)
                if rep:
                    slack_out["monthly"] = send_monthly_report_link(
                        rep, campaign_id=campaign_id, dry_run=slack_dry_run
                    )
                    sent_monthly.append(mk)

    manifest["slack_sent_weekly_keys"] = sent_weekly
    manifest["slack_sent_monthly_keys"] = sent_monthly
    manifest["slack"] = slack_out if send_slack_reports else {"skipped": True}
    manifest["ok"] = leakage_summary != "FAIL" and manifest.get("error") is None
    manifest["chunk_processed_dates"] = chunk_new_dates
    manifest["chunk_size_trading_days"] = chunk_size
    manifest["needs_resume"] = not campaign_complete and not full_audit_ended
    manifest["execution_mode"] = os.environ.get("COMPETITION_EXECUTION_MODE")
    manifest["trading_dates"] = planned_dates
    manifest["start_date"] = planned_dates[0]
    manifest["end_date"] = planned_dates[-1]

    manifest["campaign_id"] = campaign_id
    if resume_existing_campaign and str(campaign_id) != requested_campaign_id:
        return {
            "ok": False,
            "error": "resume_campaign_id_mismatch_after_run",
            "requested_campaign_id": requested_campaign_id,
            "result_campaign_id": campaign_id,
        }
    sync_manifest_progress(campaign_id, manifest, checkpoint, planned_dates=planned_dates)

    from src.trading.competition.replay.observability import CampaignObservability

    camp_obs = CampaignObservability(campaign_id, replay_type=replay_type)
    camp_status = "failed" if not manifest.get("ok") else (
        "completed" if not manifest.get("needs_resume") else "partial"
    )
    camp_obs.log_chunk(
        status=camp_status,
        chunk_dates=list(manifest.get("chunk_processed_dates") or []),
        failure_summary=manifest.get("error") if not manifest.get("ok") else None,
        manifest=manifest,
    )
    camp_obs.finalize_campaign_meta(
        manifest,
        status=camp_status,
        failure_summary=manifest.get("error") if not manifest.get("ok") else None,
        force_mock=force_mock,
    )

    sync_replay_campaign(campaign_id, manifest)
    return manifest
