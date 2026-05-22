# -*- coding: utf-8 -*-
"""긴급 판단 후보 큐 — 실시간 감시 신호 (자동매수 없음)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
ALERTS_PATH = ROOT / "data" / "mock_trading" / "intraday_alert_candidates.json"


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _load() -> dict[str, Any]:
    if not ALERTS_PATH.is_file():
        return {"candidates": [], "updatedAt": ""}
    return json.loads(ALERTS_PATH.read_text(encoding="utf-8"))


def _save(doc: dict[str, Any]) -> None:
    doc["updatedAt"] = _now_iso()
    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_candidates(*, status: str | None = "OPEN") -> list[dict[str, Any]]:
    rows = list(_load().get("candidates") or [])
    if status is None:
        return rows
    return [r for r in rows if str(r.get("status")) == status]


def append_candidate(signal: dict[str, Any]) -> dict[str, Any]:
    doc = _load()
    rows: list[dict[str, Any]] = list(doc.get("candidates") or [])
    row = dict(signal)
    row.setdefault("candidate_id", str(uuid.uuid4()))
    row.setdefault("status", "OPEN")
    row.setdefault("created_at", _now_iso())
    rows.append(row)
    doc["candidates"] = rows[-200:]
    _save(doc)
    return row


def close_candidate(candidate_id: str, *, status: str, detail: dict[str, Any] | None = None) -> None:
    doc = _load()
    for row in doc.get("candidates") or []:
        if str(row.get("candidate_id")) == candidate_id:
            row["status"] = status
            row["closed_at"] = _now_iso()
            if detail:
                row["result"] = detail
            break
    _save(doc)
