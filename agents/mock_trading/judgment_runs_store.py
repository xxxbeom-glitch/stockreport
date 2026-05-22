# -*- coding: utf-8 -*-
"""정기·긴급 AI 판단 실행 기록."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "data" / "mock_trading" / "judgment_runs"


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def judgment_run_id(entry_type: str, at: datetime | None = None) -> str:
    at = (at or datetime.now(KST)).astimezone(KST)
    return f"{at.strftime('%Y-%m-%dT%H:%M')}_{entry_type}"


def save_run(record: dict[str, Any]) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    rid = str(record.get("judgment_run_id") or judgment_run_id("UNKNOWN"))
    safe = rid.replace(":", "-")
    path = RUNS_DIR / f"{safe}.json"
    record.setdefault("recorded_at", _now_iso())
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_run(judgment_run_id: str) -> dict[str, Any] | None:
    safe = judgment_run_id.replace(":", "-")
    path = RUNS_DIR / f"{safe}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
