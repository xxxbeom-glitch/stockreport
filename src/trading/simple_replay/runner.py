"""Single-shot SIMPLE_REPLAY orchestration."""

from __future__ import annotations

import os
import uuid
from typing import Any

from src.trading.competition.models import now_kst_iso
from src.trading.simple_replay.calendar import normalize_yyyymmdd, resolve_schedule
from src.trading.simple_replay.constants import INITIAL_CASH_KRW, TEAM_IDS
from src.trading.simple_replay.dashboard_payload import build_dashboard_payload
from src.trading.simple_replay.errors import SimpleReplayError
from src.trading.simple_replay.evaluation import build_timeline, evaluate_position_horizons, team_totals
from src.trading.simple_replay.facts import build_team_candidate_inputs
from src.trading.simple_replay.leakage import check_decision_leakage
from src.trading.simple_replay.llm import run_agent_decision
from src.trading.simple_replay.paths import ensure_dirs
from src.trading.simple_replay.publish import publish_run
from src.trading.simple_replay.report import build_performance_report
from src.trading.simple_replay.storage import load_manifest, save_run_artifacts
from src.trading.simple_replay.universe import load_candidate_pool
from src.trading.simple_replay.virtual_buy import virtual_buy


def _ensure_llm_model_env() -> None:
    """Use real model IDs when env still has -placeholder defaults."""
    defaults = {
        "COMPETITION_A_MAIN_MODEL": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "COMPETITION_B_MAIN_MODEL": os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash-lite"),
        "COMPETITION_C_MAIN_MODEL": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "COMPETITION_D_MAIN_MODEL": os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash-lite"),
    }
    for key, val in defaults.items():
        cur = os.getenv(key, "")
        if not cur or cur.endswith("-placeholder"):
            os.environ[key] = val


def _kis_budget_ok_for_decisions() -> None:
    try:
        from data.kis_rate_limit import configured_max_requests_per_run, is_kis_request_budget_reached

        if is_kis_request_budget_reached():
            raise SimpleReplayError("kis_request_budget_reached")
        used = __import__("data.kis_rate_limit", fromlist=["kis_requests_used"]).kis_requests_used()
        budget = configured_max_requests_per_run()
        if used >= max(10, budget - 15):
            raise SimpleReplayError("kis_request_budget_near_limit", detail=f"{used}/{budget}")
    except ImportError:
        pass


def _find_completed_run(decision_date: str) -> dict[str, Any] | None:
    from src.trading.simple_replay.storage import list_local_runs

    for m in list_local_runs():
        if m.get("decision_date") == decision_date and m.get("status") == "completed":
            return m
    return None


def run_simple_replay(
    decision_date: str,
    *,
    observation_days: int = 5,
    force_regenerate: bool = False,
    publish_pages: bool = True,
) -> dict[str, Any]:
    """
    Run full SIMPLE_REPLAY in one shot. On failure, nothing is published as completed.
    """
    os.environ.setdefault("COMPETITION_EXECUTION_MODE", "simple_replay")
    os.environ.setdefault("KIS_MAX_REQUESTS_PER_RUN", os.getenv("SIMPLE_REPLAY_KIS_BUDGET", "60"))
    _ensure_llm_model_env()

    decision_date = normalize_yyyymmdd(decision_date)
    if not force_regenerate:
        existing = _find_completed_run(decision_date)
        if existing:
            return {"ok": True, "reused": True, "run_id": existing["run_id"], "manifest": existing}

    schedule = resolve_schedule(decision_date, observation_days)
    buy_date = str(schedule["buy_date"])
    evaluation_dates = list(schedule["evaluation_dates"])
    evaluation_horizons = dict(schedule.get("evaluation_horizons") or {})

    run_id = f"simple_replay_{decision_date}_{uuid.uuid4().hex[:8]}"
    ensure_dirs()

    try:
        pool = load_candidate_pool(decision_date)
        team_inputs, facts_meta = build_team_candidate_inputs(pool, decision_date)
        name_by = {str(r["ticker"]).zfill(6): str(r.get("name") or r["ticker"]) for r in pool}

        _kis_budget_ok_for_decisions()

        decisions: list[dict[str, Any]] = []
        for tid in TEAM_IDS:
            dec = run_agent_decision(
                tid,
                decision_date=decision_date,
                candidates=team_inputs.get(tid, []),
                run_id=run_id,
            )
            leak = check_decision_leakage(dec, decision_date)
            if not leak["ok"]:
                raise SimpleReplayError("future_data_leakage", detail=";".join(leak["items"][:5]))
            if dec.get("used_mock") and os.getenv("SIMPLE_REPLAY_ALLOW_MOCK", "").lower() not in ("1", "true", "yes"):
                raise SimpleReplayError("mock_llm_not_allowed", detail=f"team={tid}")
            decisions.append(dec)

        positions: list[dict[str, Any]] = []
        for dec in decisions:
            pos = virtual_buy(dec, buy_date=buy_date, name_by_ticker=name_by)
            if pos:
                positions.append(evaluate_position_horizons(pos, evaluation_horizons))

        team_total_map: dict[str, dict[str, Any]] = {}
        team_snapshots: dict[str, list[int]] = {}
        for tid in TEAM_IDS:
            pos = next((p for p in positions if p["team_id"] == tid), None)
            skip = not pos
            team_total_map[tid] = team_totals(tid, position=pos, skip=skip)
            if pos:
                cash = int(pos.get("remaining_cash") or 0)
                team_snapshots[tid] = [
                    cash + int(day["market_value"]) for day in pos["daily_evaluations"]
                ]
            else:
                team_snapshots[tid] = [INITIAL_CASH_KRW] * len(evaluation_dates)

        timeline = build_timeline(evaluation_dates, team_snapshots)

        manifest: dict[str, Any] = {
            "run_id": run_id,
            "status": "completed",
            "decision_date": decision_date,
            "buy_date": buy_date,
            "evaluation_dates": evaluation_dates,
            "evaluation_horizons": evaluation_horizons,
            "observation_days": observation_days,
            "facts_meta": facts_meta,
            "decision_at": schedule.get("decision_cutoff") or f"{decision_date}T15:30:00+09:00",
            "cost_model_applied": False,
            "cost_model_note": "SIMPLE_REPLAY MVP에서는 거래비용 미반영",
            "calendar_source": schedule.get("calendar_source"),
            "completed_at": now_kst_iso(),
            "notifications": [
                {
                    "notification_id": f"sr_{run_id}_done",
                    "category": "report",
                    "title": "SIMPLE REPLAY 완료",
                    "sub": f"기준일 {decision_date} · 5거래일 성과 리포트 생성",
                    "created_at": now_kst_iso(),
                    "read": False,
                }
            ],
        }

        report = build_performance_report(
            manifest=manifest,
            decisions=decisions,
            positions=positions,
            team_totals=team_total_map,
        )
        dashboard = build_dashboard_payload(
            run_id=run_id,
            manifest=manifest,
            decisions=decisions,
            positions=positions,
            team_totals=team_total_map,
            timeline=timeline,
            report=report,
        )

        save_run_artifacts(
            run_id,
            manifest=manifest,
            decisions=decisions,
            positions=positions,
            dashboard=dashboard,
            report=report,
            team_candidate_inputs={"teams": team_inputs, "meta": facts_meta},
        )
        if publish_pages:
            publish_run(run_id)

        return {
            "ok": True,
            "reused": False,
            "run_id": run_id,
            "manifest": manifest,
            "dashboard": dashboard,
            "decisions": decisions,
            "positions": positions,
        }

    except SimpleReplayError as exc:
        fail_manifest = {
            "run_id": run_id,
            "status": "failed",
            "decision_date": decision_date,
            "error": exc.code,
            "error_detail": exc.detail,
            "failed_at": now_kst_iso(),
        }
        import json
        from src.trading.simple_replay.paths import run_dir as _run_dir

        fail_path = _run_dir(run_id) / "manifest.json"
        fail_path.parent.mkdir(parents=True, exist_ok=True)
        fail_path.write_text(json.dumps(fail_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": False, "run_id": run_id, "error": exc.code, "detail": exc.detail}
