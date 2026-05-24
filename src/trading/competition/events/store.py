"""Event persistence — competition namespace only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.trading.competition.constants import COLLECTION_EVENTS
from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.base import (
    ROOT,
    append_jsonl,
    firestore_client,
    load_json_file,
    read_jsonl,
    save_json_file,
)

EVENTS_DIR = ROOT / "data" / "competition" / "events"
RAW_SIGNALS_PATH = EVENTS_DIR / "raw_signals.jsonl"
ACTIONABLE_EVENTS_PATH = EVENTS_DIR / "actionable_events.jsonl"
GATE_REJECTED_PATH = EVENTS_DIR / "gate_rejected.jsonl"
ANALYZED_EVENTS_PATH = EVENTS_DIR / "analyzed_events.jsonl"  # legacy mirror of actionable
DEDUP_INDEX_PATH = EVENTS_DIR / "dedup_index.json"
SCAN_SUMMARY_PATH = EVENTS_DIR / "scan_summary.json"


def ensure_events_dir() -> Path:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    return EVENTS_DIR


def load_dedup_index() -> dict[str, Any]:
    ensure_events_dir()
    return load_json_file(
        DEDUP_INDEX_PATH,
        {"keys": {}, "updated_at": ""},
    )


def save_dedup_index(index: dict[str, Any]) -> None:
    ensure_events_dir()
    index["updated_at"] = now_kst_iso()
    save_json_file(DEDUP_INDEX_PATH, index)


def append_raw_signal(record: dict[str, Any]) -> None:
    ensure_events_dir()
    append_jsonl(RAW_SIGNALS_PATH, record)


def append_gate_rejected(record: dict[str, Any]) -> None:
    ensure_events_dir()
    append_jsonl(GATE_REJECTED_PATH, record)


def append_actionable_event(record: dict[str, Any]) -> dict[str, Any]:
    ensure_events_dir()
    append_jsonl(ACTIONABLE_EVENTS_PATH, record)
    # Legacy compatibility — same record
    append_jsonl(ANALYZED_EVENTS_PATH, record)

    client, _status = firestore_client()
    firestore_ok = False
    if client:
        try:
            doc_id = record.get("event_id")
            ref = (
                client.collection(COLLECTION_EVENTS).document(doc_id)
                if doc_id
                else client.collection(COLLECTION_EVENTS).document()
            )
            ref.set(record)
            firestore_ok = True
        except Exception:
            pass

    return {
        "ok": True,
        "persist_backend": "firestore" if firestore_ok else "local_mirror",
        "firestore_ok": firestore_ok,
    }


def append_analyzed_event(record: dict[str, Any]) -> dict[str, Any]:
    """Deprecated alias — use append_actionable_event."""
    return append_actionable_event(record)


def load_actionable_events(limit: int = 0) -> list[dict[str, Any]]:
    rows = read_jsonl(ACTIONABLE_EVENTS_PATH)
    return rows[-limit:] if limit > 0 else rows


def load_raw_signals(limit: int = 0) -> list[dict[str, Any]]:
    rows = read_jsonl(RAW_SIGNALS_PATH)
    return rows[-limit:] if limit > 0 else rows


def load_analyzed_events(limit: int = 0) -> list[dict[str, Any]]:
    rows = read_jsonl(ANALYZED_EVENTS_PATH)
    return rows[-limit:] if limit > 0 else rows


def save_scan_summary(summary: dict[str, Any]) -> None:
    ensure_events_dir()
    save_json_file(SCAN_SUMMARY_PATH, summary)


def load_scan_summary() -> dict[str, Any]:
    ensure_events_dir()
    return load_json_file(SCAN_SUMMARY_PATH, {})
