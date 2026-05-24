"""REPLAY observability — internal audit logs + public summaries (no secrets)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.trading.competition.constants import TEAM_IDS, TEAM_META
from src.trading.competition.models import now_kst_iso
from src.trading.competition.replay.data_provider import _kis_ready, _pykrx
from src.trading.competition.runtime import COMPETITION_ROOT, replay_run_dir
from src.trading.competition.teams.config import ROLE_CONFIG, provider_available, resolve_model

KST = ZoneInfo("Asia/Seoul")
CAMPAIGNS_ROOT = COMPETITION_ROOT / "replay" / "campaigns"

_REDACT_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|webhook|password|credential|authorization|private_key|service_account)",
    re.I,
)
_SECRET_VALUE_RE = re.compile(
    r"(sk-[a-zA-Z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|Bearer\s+\S+|https?://hooks\.slack\.com/\S+)",
    re.I,
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        if _SECRET_VALUE_RE.search(value):
            return "[REDACTED]"
        if len(value) > 2000:
            return value[:2000] + "…[truncated]"
        return value
    if isinstance(value, dict):
        return redact_record(value)
    if isinstance(value, list):
        return [redact_value(v) for v in value[:200]]
    return value


def redact_record(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in record.items():
        if _REDACT_KEY_RE.search(str(key)):
            out[key] = "[REDACTED]"
            continue
        out[key] = redact_value(value)
    return out


def workflow_run_context() -> dict[str, Any]:
    """GitHub Actions / CI identifiers only — never tokens."""
    return redact_record(
        {
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
            "github_workflow": os.getenv("GITHUB_WORKFLOW"),
            "github_job": os.getenv("GITHUB_JOB"),
            "github_repository": os.getenv("GITHUB_REPOSITORY"),
            "github_ref": os.getenv("GITHUB_REF"),
            "github_sha": (os.getenv("GITHUB_SHA") or "")[:12] or None,
        }
    )


def providers_configuration() -> dict[str, Any]:
    return {
        "market_data_primary": "KIS",
        "market_data_fallback": "pykrx",
        "kis_configured": bool(_kis_ready()),
        "pykrx_available": _pykrx() is not None,
    }


def model_configuration_summary(*, force_mock: bool = False) -> dict[str, Any]:
    teams: dict[str, Any] = {}
    for tid in TEAM_IDS:
        main_role = f"{tid}_MAIN"
        partner_role = f"{tid}_PARTNER" if tid in ("A", "B") else f"{tid}_VALIDATOR"
        main_provider, main_model = resolve_model(main_role, force_mock=force_mock)
        partner_provider, partner_model = resolve_model(partner_role, force_mock=force_mock)
        teams[tid] = {
            "strategy_label": TEAM_META[tid]["strategy_label"],
            "type_label": TEAM_META[tid]["type_label"],
            "main": {
                "role": main_role,
                "provider": main_provider,
                "model": main_model,
                "provider_available": provider_available(main_provider),
            },
            "partner_or_validator": {
                "role": partner_role,
                "provider": partner_provider,
                "model": partner_model,
                "provider_available": provider_available(partner_provider),
            },
        }
    return {
        "force_mock": force_mock,
        "execution_mode": os.getenv("COMPETITION_EXECUTION_MODE"),
        "teams": teams,
        "role_env_keys": [cfg.model_env_key for cfg in ROLE_CONFIG.values()],
    }


def compute_strategy_differentiation(
    decisions_out: list[dict[str, Any]],
    *,
    team_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for item in decisions_out:
        decision = item.get("decision") or {}
        tid = str(decision.get("team_id") or "")
        meta = TEAM_META.get(tid) or {}
        review = item.get("review") or {}
        profiles.append(
            {
                "team_id": tid,
                "strategy_label": meta.get("strategy_label"),
                "type_label": meta.get("type_label"),
                "action": decision.get("action"),
                "ticker": decision.get("ticker"),
                "review_result": review.get("result") if review else None,
                "fill_status": (team_results or {}).get(tid, {}).get("status"),
            }
        )

    signatures = {
        (p["team_id"], p.get("action"), p.get("ticker"))
        for p in profiles
        if p.get("team_id")
    }
    actions = [p.get("action") for p in profiles]
    all_hold = bool(actions) and all(a in (None, "HOLD", "WAIT", "") for a in actions)
    buy_teams = {p["team_id"] for p in profiles if p.get("action") in ("BUY", "ADD_BUY")}
    verify_blocks = sum(
        1
        for p in profiles
        if p.get("type_label") == "검증승인" and p.get("review_result") in ("REJECT", "HOLD")
    )

    divergence = 0.0
    if profiles and not all_hold:
        divergence = min(1.0, len(signatures) / max(1, len(TEAM_IDS)))

    return {
        "teams_evaluated": len(profiles),
        "unique_action_profiles": len(signatures),
        "all_hold": all_hold,
        "divergence_score": round(divergence, 2),
        "buy_team_count": len(buy_teams),
        "verify_reject_or_hold_count": verify_blocks,
        "profiles": profiles,
    }


def _public_strategy_summary(diff: dict[str, Any]) -> dict[str, Any]:
    return {
        "teamsEvaluated": diff.get("teams_evaluated"),
        "uniqueActionProfiles": diff.get("unique_action_profiles"),
        "divergenceScore": diff.get("divergence_score"),
        "allHold": diff.get("all_hold"),
        "buyTeamCount": diff.get("buy_team_count"),
    }


class RunObservability:
    """Per replay_run_id internal logs under observability/."""

    def __init__(
        self,
        replay_run_id: str,
        *,
        campaign_id: str | None = None,
        replay_type: str | None = None,
        trading_date: str | None = None,
    ) -> None:
        self.replay_run_id = replay_run_id
        self.campaign_id = campaign_id
        self.replay_type = replay_type
        self.trading_date = trading_date
        self.root = replay_run_dir(replay_run_id) / "observability"
        self.root.mkdir(parents=True, exist_ok=True)
        self.started_at = now_kst_iso()
        self._event_count = 0
        self._errors: list[str] = []

    def _append_jsonl(self, name: str, record: dict[str, Any]) -> None:
        path = self.root / name
        safe = redact_record({**record, "ts": now_kst_iso()})
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")

    def log_pipeline(
        self,
        stage: str,
        status: str,
        *,
        detail: str | None = None,
        **extra: Any,
    ) -> None:
        self._event_count += 1
        if status in ("error", "failed") and detail:
            self._errors.append(f"{stage}:{detail}"[:500])
        rec: dict[str, Any] = {"stage": stage, "status": status}
        if detail:
            rec["detail"] = detail
        rec.update(extra)
        self._append_jsonl("pipeline_events.jsonl", rec)

    def log_api_connection(
        self,
        service: str,
        *,
        ok: bool,
        primary: str | None = None,
        fallback: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        self.log_pipeline(
            "api_connection",
            "ok" if ok else "error",
            service=service,
            primary=primary,
            fallback=fallback,
            error_summary=error_summary,
        )

    def log_strategy_trace(
        self,
        *,
        team_id: str,
        decision: dict[str, Any],
        review: dict[str, Any] | None = None,
        audit: dict[str, Any] | None = None,
        fill_status: str | None = None,
    ) -> None:
        meta = TEAM_META.get(team_id) or {}
        self._append_jsonl(
            "strategy_trace.jsonl",
            {
                "team_id": team_id,
                "strategy_label": meta.get("strategy_label"),
                "type_label": meta.get("type_label"),
                "action": decision.get("action"),
                "ticker": decision.get("ticker"),
                "review_result": (review or {}).get("result"),
                "leakage_status": (decision.get("leakage_audit") or {}).get("status"),
                "audit_ok": (audit or {}).get("ok"),
                "fill_status": fill_status,
            },
        )

    def finalize(
        self,
        manifest: dict[str, Any],
        *,
        status: str,
        failure_summary: str | None = None,
        strategy_diff: dict[str, Any] | None = None,
        force_mock: bool = False,
        campaign_progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ended_at = now_kst_iso()
        providers = providers_configuration()
        models = model_configuration_summary(force_mock=force_mock)
        cost_model = str(manifest.get("cost_model") or "costs_not_implemented")
        cost_applied = manifest.get("costs_applied") is True

        meta: dict[str, Any] = {
            "schema_version": 1,
            "campaign_id": self.campaign_id or manifest.get("campaign_id"),
            "replay_run_id": self.replay_run_id,
            "replay_type": self.replay_type,
            "trading_date": self.trading_date or manifest.get("trading_date"),
            "execution_mode": os.getenv("COMPETITION_EXECUTION_MODE"),
            "models": models,
            "providers": providers,
            "workflow": workflow_run_context(),
            "timing": {"started_at": self.started_at, "ended_at": ended_at},
            "affects_live_account": False,
            "cost_model": "applied" if cost_applied else "not_implemented",
            "costs_applied": cost_applied,
            "status": status,
            "failure_summary": failure_summary,
            "leakage_summary": manifest.get("leakage_summary"),
            "code_audit_failures": manifest.get("code_audit_failures"),
            "pipeline_event_count": self._event_count,
            "error_summaries": self._errors[:20],
            "campaign_progress": campaign_progress,
        }
        if strategy_diff:
            meta["strategy_differentiation"] = strategy_diff
            _write_json(self.root / "strategy_differentiation.json", strategy_diff)

        _write_json(self.root / "execution_meta.json", meta)
        public = build_public_audit_summary(meta, manifest)
        _write_json(self.root / "public_audit_summary.json", public)
        return meta

    def load_public_audit_summary(self) -> dict[str, Any]:
        return _read_json(self.root / "public_audit_summary.json")


def build_public_audit_summary(
    execution_meta: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Sanitized summary safe for GitHub Pages / dashboard."""
    providers = execution_meta.get("providers") or {}
    provider_bits = []
    if providers.get("kis_configured"):
        provider_bits.append("KIS")
    if providers.get("pykrx_available"):
        provider_bits.append("pykrx")
    providers_summary = " + ".join(provider_bits) if provider_bits else "unavailable"

    diff = execution_meta.get("strategy_differentiation") or {}
    progress = execution_meta.get("campaign_progress") or {}
    errors = execution_meta.get("error_summaries") or []
    status = execution_meta.get("status") or "unknown"
    pipeline_health = "ok"
    if errors or status == "failed":
        pipeline_health = "degraded" if status != "failed" else "failed"

    leakage = manifest.get("leakage_summary") or execution_meta.get("leakage_summary") or "UNVERIFIED"
    code_failures = int(manifest.get("code_audit_failures") or execution_meta.get("code_audit_failures") or 0)
    cost_model = execution_meta.get("cost_model") or "not_implemented"
    costs_not_implemented = cost_model == "not_implemented"

    committee = manifest.get("committee") or {}
    committee_status = "skipped" if committee.get("skipped") else (
        "completed" if committee.get("verdict") or committee.get("summary") else "not_run"
    )

    return {
        "observabilityVersion": 1,
        "replayRunId": execution_meta.get("replay_run_id"),
        "campaignId": execution_meta.get("campaign_id"),
        "tradingDate": execution_meta.get("trading_date"),
        "status": status,
        "failureSummary": execution_meta.get("failure_summary"),
        "leakageStatus": leakage,
        "ruleViolationCount": code_failures,
        "committeeStatus": committee_status,
        "providersSummary": providers_summary,
        "pipelineHealth": pipeline_health,
        "pipelineEventCount": execution_meta.get("pipeline_event_count"),
        "errorCount": len(errors),
        "strategyDifferentiation": _public_strategy_summary(diff),
        "processedDays": progress.get("days_completed"),
        "totalDays": progress.get("days_total"),
        "progressLabel": progress.get("progress_label"),
        "costModel": cost_model,
        "costsWarning": (
            "매매 수수료·세금·제비용 미반영 — REPLAY 총자산·수익률은 비용 제외 기준"
            if costs_not_implemented
            else None
        ),
        "affectsLiveAccount": False,
        "modelsForceMock": (execution_meta.get("models") or {}).get("force_mock"),
    }


class CampaignObservability:
    """Campaign-level meta + chunk audit trail."""

    def __init__(self, campaign_id: str, *, replay_type: str) -> None:
        self.campaign_id = campaign_id
        self.replay_type = replay_type
        self.root = CAMPAIGNS_ROOT / campaign_id / "observability"
        self.root.mkdir(parents=True, exist_ok=True)
        self.started_at = now_kst_iso()

    def _append_jsonl(self, name: str, record: dict[str, Any]) -> None:
        path = self.root / name
        safe = redact_record({**record, "ts": now_kst_iso()})
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")

    def log_chunk(
        self,
        *,
        status: str,
        chunk_dates: list[str],
        failure_summary: str | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        self._append_jsonl(
            "chunk_events.jsonl",
            {
                "status": status,
                "chunk_dates": chunk_dates,
                "failure_summary": failure_summary,
                "days_completed": (manifest or {}).get("days_completed"),
                "days_total": (manifest or {}).get("days_total"),
                "competition_status": (manifest or {}).get("competition_status"),
            },
        )

    def finalize_campaign_meta(
        self,
        manifest: dict[str, Any],
        *,
        status: str,
        failure_summary: str | None = None,
        force_mock: bool = False,
    ) -> dict[str, Any]:
        meta = {
            "schema_version": 1,
            "campaign_id": self.campaign_id,
            "replay_type": self.replay_type,
            "execution_mode": os.getenv("COMPETITION_EXECUTION_MODE"),
            "models": model_configuration_summary(force_mock=force_mock),
            "providers": providers_configuration(),
            "workflow": workflow_run_context(),
            "timing": {"started_at": self.started_at, "ended_at": now_kst_iso()},
            "affects_live_account": False,
            "cost_model": "not_implemented",
            "processed_days": manifest.get("days_completed"),
            "total_days": manifest.get("days_total"),
            "progress_label": manifest.get("progress_label"),
            "competition_status": manifest.get("competition_status"),
            "needs_resume": manifest.get("needs_resume"),
            "status": status,
            "failure_summary": failure_summary,
            "run_ids": manifest.get("run_ids"),
            "weekly_report_keys": manifest.get("weekly_report_keys"),
            "monthly_report_keys": manifest.get("monthly_report_keys"),
        }
        _write_json(self.root / "campaign_execution_meta.json", meta)
        public = build_public_campaign_audit_summary(meta, manifest)
        _write_json(self.root / "public_audit_summary.json", public)
        return meta


def build_public_campaign_audit_summary(
    execution_meta: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    providers = execution_meta.get("providers") or {}
    bits = []
    if providers.get("kis_configured"):
        bits.append("KIS")
    if providers.get("pykrx_available"):
        bits.append("pykrx")
    return {
        "observabilityVersion": 1,
        "campaignId": execution_meta.get("campaign_id"),
        "replayType": execution_meta.get("replay_type"),
        "status": execution_meta.get("status"),
        "competitionStatus": manifest.get("competition_status"),
        "failureSummary": execution_meta.get("failure_summary"),
        "processedDays": execution_meta.get("processed_days"),
        "totalDays": execution_meta.get("total_days"),
        "progressLabel": execution_meta.get("progress_label"),
        "needsResume": manifest.get("needs_resume"),
        "providersSummary": " + ".join(bits) if bits else "unavailable",
        "leakageSummary": manifest.get("leakage_summary"),
        "costModel": "not_implemented",
        "affectsLiveAccount": False,
        "runCount": len(manifest.get("run_ids") or []),
    }


def load_run_public_audit_summary(replay_run_id: str) -> dict[str, Any]:
    path = replay_run_dir(replay_run_id) / "observability" / "public_audit_summary.json"
    return _read_json(path)


def load_campaign_public_audit_summary(campaign_id: str) -> dict[str, Any]:
    path = CAMPAIGNS_ROOT / campaign_id / "observability" / "public_audit_summary.json"
    return _read_json(path)


def merge_public_audit_into_dashboard(audit_summary: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if not public:
        return audit_summary
    merged = dict(audit_summary)
    merged["pipelineHealth"] = public.get("pipelineHealth")
    merged["providersSummary"] = public.get("providersSummary")
    merged["strategyDifferentiation"] = public.get("strategyDifferentiation")
    merged["observabilityStatus"] = public.get("status")
    merged["failureSummary"] = public.get("failureSummary")
    merged["pipelineEventCount"] = public.get("pipelineEventCount")
    merged["errorCount"] = public.get("errorCount")
    merged["progressLabel"] = public.get("progressLabel") or merged.get("progressLabel")
    return merged
