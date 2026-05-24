"""REPLAY batch checkpoint — KIS request budget and auto-resume status."""

from __future__ import annotations

from typing import Any

from src.trading.competition.models import now_kst_iso

STATUS_CHECKPOINT_WAITING = "checkpoint_waiting_resume"
STATUS_ACTIVE = "active"
STATUS_NEEDS_REVIEW = "needs_manual_review"
STATUS_RATE_LIMIT_PAUSED = "kis_rate_limit_paused"

RESUME_REASON_BUDGET = "kis_request_budget_reached"
RESUME_REASON_RATE_LIMIT = "kis_rate_limit_exceeded"

# Do not auto-retry via cron — require human intervention.
FATAL_NO_AUTO_RETRY_ERRORS = frozenset(
    {
        "kis_auth_failed",
        "kis_credentials_missing",
        "campaign_id_required_for_resume",
        "campaign_not_found",
        "campaign_not_found_firestore",
        "campaign_hydrate_failed",
        "campaign_marked_duplicate_do_not_resume",
        "campaign_already_ended",
        "data_invalid",
        "leakage_fail",
        "firestore_sync_failed",
    }
)

AUTO_RESUMABLE_STATUSES = frozenset(
    {
        STATUS_ACTIVE,
        STATUS_CHECKPOINT_WAITING,
        STATUS_RATE_LIMIT_PAUSED,
        "active",
    }
)


def public_batch_status(manifest: dict[str, Any]) -> str:
    """Dashboard-facing status label."""
    err = str(manifest.get("error") or "")
    if manifest.get("do_not_resume"):
        return "중단(중복 캠페인)"
    status = str(manifest.get("competition_status") or manifest.get("batch_status") or "")
    if status in ("ended", "month_completed"):
        return "완료"
    if status == STATUS_NEEDS_REVIEW or err in FATAL_NO_AUTO_RETRY_ERRORS:
        return "확인 필요 오류"
    if status == STATUS_RATE_LIMIT_PAUSED:
        return "자동 재개 대기(KIS 제한)"
    if status == STATUS_CHECKPOINT_WAITING:
        return "자동 재개 대기"
    if manifest.get("needs_resume"):
        return "진행중"
    return "완료"


def attach_batch_progress(
    manifest: dict[str, Any],
    *,
    kis_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from data.kis_rate_limit import (
        configured_max_requests_per_run,
        is_kis_request_budget_reached,
        kis_rate_limit_observability,
        kis_requests_used,
    )

    summary = kis_summary or kis_rate_limit_observability()
    manifest["kis_requests_used"] = kis_requests_used()
    manifest["kis_requests_budget"] = configured_max_requests_per_run()
    manifest["configured_rps"] = summary.get("configured_rps")
    manifest["last_batch_kis_requests"] = summary.get("total_http_requests")
    manifest["last_batch_max_rps_observed"] = summary.get("actual_max_requests_in_rolling_1s")
    manifest["last_batch_at"] = now_kst_iso()
    manifest["batch_status"] = manifest.get("batch_status") or manifest.get("competition_status")
    manifest["public_status"] = public_batch_status(manifest)
    if is_kis_request_budget_reached():
        manifest["resume_reason"] = RESUME_REASON_BUDGET
    return manifest


def apply_request_budget_checkpoint(
    manifest: dict[str, Any],
    *,
    campaign_id: str,
    chunk_processed_dates: list[str] | None = None,
) -> dict[str, Any]:
    from data.kis_rate_limit import kis_requests_used

    manifest.update(
        {
            "ok": True,
            "campaign_id": campaign_id,
            "needs_resume": True,
            "competition_status": STATUS_CHECKPOINT_WAITING,
            "batch_status": STATUS_CHECKPOINT_WAITING,
            "resume_reason": RESUME_REASON_BUDGET,
            "error": None,
            "failed_trading_date": None,
            "chunk_processed_dates": list(chunk_processed_dates or []),
            "kis_requests_used": kis_requests_used(),
        }
    )
    return attach_batch_progress(manifest)


def apply_rate_limit_pause(
    manifest: dict[str, Any],
    *,
    campaign_id: str,
    failed_trading_date: str,
    chunk_processed_dates: list[str] | None = None,
    day_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest.update(
        {
            "ok": True,
            "campaign_id": campaign_id,
            "needs_resume": True,
            "competition_status": STATUS_RATE_LIMIT_PAUSED,
            "batch_status": STATUS_RATE_LIMIT_PAUSED,
            "resume_reason": RESUME_REASON_RATE_LIMIT,
            "error": RESUME_REASON_RATE_LIMIT,
            "failed_trading_date": failed_trading_date,
            "chunk_processed_dates": list(chunk_processed_dates or []),
            "kis_rate_limit": (day_result or {}).get("kis_rate_limit"),
        }
    )
    return attach_batch_progress(manifest)


def apply_fatal_stop(
    manifest: dict[str, Any],
    *,
    campaign_id: str,
    error: str,
    failed_trading_date: str | None = None,
    chunk_processed_dates: list[str] | None = None,
) -> dict[str, Any]:
    manifest.update(
        {
            "ok": False,
            "campaign_id": campaign_id,
            "needs_resume": False,
            "competition_status": STATUS_NEEDS_REVIEW,
            "batch_status": STATUS_NEEDS_REVIEW,
            "resume_reason": None,
            "error": error,
            "failed_trading_date": failed_trading_date,
            "chunk_processed_dates": list(chunk_processed_dates or []),
        }
    )
    manifest["public_status"] = public_batch_status(manifest)
    return manifest


def is_budget_checkpoint_result(result: dict[str, Any]) -> bool:
    return (
        result.get("batch_status") == STATUS_CHECKPOINT_WAITING
        or result.get("resume_reason") == RESUME_REASON_BUDGET
        or result.get("error") == RESUME_REASON_BUDGET
    )


def is_rate_limit_pause_result(result: dict[str, Any]) -> bool:
    return (
        result.get("batch_status") == STATUS_RATE_LIMIT_PAUSED
        or result.get("error") == RESUME_REASON_RATE_LIMIT
    )


def should_auto_resume(manifest: dict[str, Any]) -> bool:
    if manifest.get("do_not_resume"):
        return False
    status = str(manifest.get("competition_status") or "")
    if status in ("ended", "month_completed", "superseded", STATUS_NEEDS_REVIEW):
        return False
    err = str(manifest.get("error") or "")
    if err in FATAL_NO_AUTO_RETRY_ERRORS:
        return False
    if status in AUTO_RESUMABLE_STATUSES or manifest.get("needs_resume"):
        return True
    return False
