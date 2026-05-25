"""Publish completed SIMPLE_REPLAY runs to docs/simple-replay-data."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.trading.simple_replay.paths import SIMPLE_REPLAY_PAGES_ROOT, run_dir


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rebuild_index() -> Path:
    """Index only completed runs."""
    from src.trading.simple_replay.storage import list_local_runs

    runs_meta = []
    for m in list_local_runs():
        if m.get("status") != "completed":
            continue
        runs_meta.append(
            {
                "runId": m.get("run_id"),
                "decisionDate": m.get("decision_date"),
                "buyDate": m.get("buy_date"),
                "observationDays": m.get("observation_days"),
                "completedAt": m.get("completed_at"),
                "dashboardPath": f"runs/{m.get('run_id')}/dashboard.json",
            }
        )
    index = {"runs": runs_meta, "updatedAt": __import__("datetime").datetime.now().isoformat()}
    _write(SIMPLE_REPLAY_PAGES_ROOT / "index.json", index)
    return SIMPLE_REPLAY_PAGES_ROOT / "index.json"


def publish_run(run_id: str) -> None:
    src = run_dir(run_id)
    if not src.is_dir():
        return
    dest = SIMPLE_REPLAY_PAGES_ROOT / "runs" / run_id
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "dashboard.json", "decisions.json", "positions.json", "report.json"):
        sp = src / name
        if sp.is_file():
            shutil.copy2(sp, dest / name)
    rebuild_index()


def list_completed_runs() -> list[dict[str, Any]]:
    index_path = SIMPLE_REPLAY_PAGES_ROOT / "index.json"
    if index_path.is_file():
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return list(data.get("runs") or [])
    return []
