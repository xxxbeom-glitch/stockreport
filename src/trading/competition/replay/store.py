"""Isolated REPLAY persistence — never writes LIVE paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.trading.competition.runtime import replay_run_dir


class ReplayStore:
    def __init__(self, replay_run_id: str) -> None:
        self.replay_run_id = replay_run_id
        self.root = replay_run_dir(replay_run_id)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / name

    def save_json(self, name: str, payload: Any) -> None:
        p = self._path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def append_jsonl(self, name: str, record: dict[str, Any]) -> None:
        p = self._path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.save_json("snapshot.json", snapshot)

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        self.save_json("manifest.json", manifest)

    def save_audit_report(self, report: dict[str, Any]) -> None:
        self.save_json("audit/code_audit_summary.json", report)

    def save_committee_report(self, report: dict[str, Any]) -> None:
        self.save_json("audit/committee_report.json", report)
