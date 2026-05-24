"""Append-only JSONL stores for decisions, orders, trades, etc."""

from __future__ import annotations

from typing import Any

from src.trading.competition.constants import (
    COLLECTION_AI_USAGE_LOGS,
    COLLECTION_DECISIONS,
    COLLECTION_EVENTS,
    COLLECTION_NOTIFICATIONS,
    COLLECTION_ORDERS,
    COLLECTION_TRADES,
)
from src.trading.competition.storage.base import (
    append_jsonl,
    ensure_local_dir,
    firestore_client,
    read_jsonl,
)

LOCAL_DIR = ensure_local_dir()


def _append_with_firestore(
    local_path,
    collection: str,
    record: dict[str, Any],
    doc_id_key: str,
) -> dict[str, Any]:
    append_jsonl(local_path, record)

    client, status = firestore_client()
    firestore_ok = False
    firestore_error = status.get("error", "")
    if client:
        try:
            doc_id = record.get(doc_id_key) or None
            ref = (
                client.collection(collection).document(doc_id)
                if doc_id
                else client.collection(collection).document()
            )
            ref.set(record)
            firestore_ok = True
        except Exception as exc:
            firestore_error = f"{type(exc).__name__}:{exc}"

    return {
        "ok": True,
        "persist_backend": "firestore" if firestore_ok else "local_mirror",
        "firestore_ok": firestore_ok,
        "firestore_error": firestore_error,
    }


def append_decision(record: dict[str, Any]) -> dict[str, Any]:
    return _append_with_firestore(
        LOCAL_DIR / "decisions.jsonl", COLLECTION_DECISIONS, record, "decision_id"
    )


def append_order(record: dict[str, Any]) -> dict[str, Any]:
    return _append_with_firestore(
        LOCAL_DIR / "orders.jsonl", COLLECTION_ORDERS, record, "order_id"
    )


def append_trade(record: dict[str, Any]) -> dict[str, Any]:
    return _append_with_firestore(
        LOCAL_DIR / "trades.jsonl", COLLECTION_TRADES, record, "trade_id"
    )


def append_event(record: dict[str, Any]) -> dict[str, Any]:
    return _append_with_firestore(
        LOCAL_DIR / "events.jsonl", COLLECTION_EVENTS, record, "event_id"
    )


def append_notification(record: dict[str, Any]) -> dict[str, Any]:
    return _append_with_firestore(
        LOCAL_DIR / "notifications.jsonl",
        COLLECTION_NOTIFICATIONS,
        record,
        "notification_id",
    )


def append_ai_usage_log(record: dict[str, Any]) -> dict[str, Any]:
    return _append_with_firestore(
        LOCAL_DIR / "ai_usage_logs.jsonl",
        COLLECTION_AI_USAGE_LOGS,
        record,
        "log_id",
    )


def load_decisions() -> list[dict[str, Any]]:
    return read_jsonl(LOCAL_DIR / "decisions.jsonl")


def load_trades() -> list[dict[str, Any]]:
    return read_jsonl(LOCAL_DIR / "trades.jsonl")


def load_notifications() -> list[dict[str, Any]]:
    return read_jsonl(LOCAL_DIR / "notifications.jsonl")
