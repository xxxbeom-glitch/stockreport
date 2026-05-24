"""Event deduplication by evidence_id and signal key."""

from __future__ import annotations

import hashlib
from typing import Any

from src.trading.competition.events.models import RawSignal
from src.trading.competition.events.store import load_dedup_index, save_dedup_index


def signal_dedup_key(signal: RawSignal) -> str:
    """Stable key for dedup — evidence + type + ticker."""
    parts = [
        signal.event_type,
        signal.ticker,
        signal.evidence.evidence_id,
        signal.scope,
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def event_dedup_key(event_id: str) -> str:
    return event_id


def is_duplicate_signal(signal: RawSignal, index: dict[str, Any] | None = None) -> bool:
    idx = index if index is not None else load_dedup_index()
    keys = idx.get("keys") or {}
    return signal_dedup_key(signal) in keys


def register_signal(signal: RawSignal, index: dict[str, Any] | None = None) -> dict[str, Any]:
    idx = index if index is not None else load_dedup_index()
    keys = idx.setdefault("keys", {})
    key = signal_dedup_key(signal)
    keys[key] = {
        "signal_id": signal.signal_id,
        "event_type": signal.event_type,
        "ticker": signal.ticker,
        "evidence_id": signal.evidence.evidence_id,
        "registered_at": signal.detected_at,
    }
    if index is None:
        save_dedup_index(idx)
    return idx


def filter_new_signals(
    signals: list[RawSignal],
) -> tuple[list[RawSignal], list[RawSignal]]:
    """Return (new_signals, duplicate_signals)."""
    index = load_dedup_index()
    new_list: list[RawSignal] = []
    dup_list: list[RawSignal] = []
    for sig in signals:
        if is_duplicate_signal(sig, index):
            dup_list.append(sig)
        else:
            new_list.append(sig)
            register_signal(sig, index)
    save_dedup_index(index)
    return new_list, dup_list
