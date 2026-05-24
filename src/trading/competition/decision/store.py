"""Decision trigger persistence."""

from __future__ import annotations

from typing import Any

from src.trading.competition.storage.base import append_jsonl, ensure_local_dir, read_jsonl, save_json_file

DECISION_DIR = ensure_local_dir() / "decision"
TRIGGERS_PATH = DECISION_DIR / "decision_triggers.jsonl"
TRIGGER_SUMMARY_PATH = DECISION_DIR / "trigger_summary.json"


def ensure_decision_dir():
    DECISION_DIR.mkdir(parents=True, exist_ok=True)
    return DECISION_DIR


def append_trigger(record: dict[str, Any]) -> None:
    ensure_decision_dir()
    append_jsonl(TRIGGERS_PATH, record)


def save_trigger_batch(triggers: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    ensure_decision_dir()
    for rec in triggers:
        append_jsonl(TRIGGERS_PATH, rec)
    save_json_file(TRIGGER_SUMMARY_PATH, summary)


def load_decision_triggers(limit: int = 0) -> list[dict[str, Any]]:
    rows = read_jsonl(TRIGGERS_PATH)
    return rows[-limit:] if limit > 0 else rows


def load_triggers_for_session(session_id: str) -> list[dict[str, Any]]:
    return [t for t in load_decision_triggers() if t.get("session_id") == session_id]
