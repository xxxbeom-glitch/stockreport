"""HTTP/API helpers for SIMPLE_REPLAY dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.trading.simple_replay.paths import SIMPLE_REPLAY_PAGES_ROOT, run_dir
from src.trading.simple_replay.publish import list_completed_runs
from src.trading.simple_replay.storage import list_local_runs


def list_runs_for_dashboard() -> list[dict[str, Any]]:
    """Only completed runs (never failed / in-progress)."""
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    for m in list_completed_runs():
        rid = str(m.get("runId") or "")
        if rid and rid not in seen:
            seen.add(rid)
            rows.append(
                {
                    "runId": rid,
                    "decisionDate": m.get("decisionDate"),
                    "buyDate": m.get("buyDate"),
                    "observationDays": m.get("observationDays"),
                    "status": "completed",
                }
            )

    for m in list_local_runs():
        if m.get("status") != "completed":
            continue
        rid = str(m.get("run_id") or "")
        if rid in seen:
            continue
        seen.add(rid)
        rows.append(
            {
                "runId": rid,
                "decisionDate": m.get("decision_date"),
                "buyDate": m.get("buy_date"),
                "observationDays": m.get("observation_days"),
                "status": "completed",
            }
        )

    rows.sort(key=lambda r: (r.get("decisionDate") or "", r.get("runId") or ""), reverse=True)
    return rows


def load_dashboard_for_run(run_id: str) -> dict[str, Any]:
    for base in (run_dir(run_id), SIMPLE_REPLAY_PAGES_ROOT / "runs" / run_id):
        path = base / "dashboard.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("simpleReplayMeta", {}).get("status") == "completed" or data.get("dataSource") == "simple_replay":
                return data
    raise FileNotFoundError(run_id)
