"""Persist SIMPLE_REPLAY run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.trading.simple_replay.paths import ensure_dirs, run_dir


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_run_artifacts(
    run_id: str,
    *,
    manifest: dict[str, Any],
    decisions: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    dashboard: dict[str, Any],
    report: dict[str, Any],
) -> Path:
    ensure_dirs()
    root = run_dir(run_id)
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "decisions.json", decisions)
    _write_json(root / "positions.json", positions)
    _write_json(root / "dashboard.json", dashboard)
    _write_json(root / "report.json", report)
    return root


def load_manifest(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "manifest.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def list_local_runs() -> list[dict[str, Any]]:
    ensure_dirs()
    from src.trading.simple_replay import paths as sr_paths

    runs_root = sr_paths.SIMPLE_REPLAY_RUNS_DIR
    rows: list[dict[str, Any]] = []
    if not runs_root.is_dir():
        return rows
    for child in runs_root.iterdir():
        if not child.is_dir():
            continue
        m = load_manifest(child.name)
        if m:
            rows.append(m)
    rows.sort(key=lambda r: (r.get("decision_date") or "", r.get("run_id") or ""), reverse=True)
    return rows
