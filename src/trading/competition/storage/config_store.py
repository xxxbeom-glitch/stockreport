"""App config storage."""

from __future__ import annotations

from typing import Any

from src.trading.competition.constants import COLLECTION_CONFIG, CONFIG_DOC_ID
from src.trading.competition.models import AppConfig, now_kst_iso
from src.trading.competition.storage.base import (
    ensure_local_dir,
    firestore_client,
    load_json_file,
    persist_result,
    save_json_file,
)

CONFIG_PATH = ensure_local_dir() / "config.json"


def load_config() -> AppConfig:
    raw = load_json_file(CONFIG_PATH, {})
    if not raw:
        return AppConfig()
    return AppConfig.from_dict(raw)


def save_config(config: AppConfig) -> dict[str, Any]:
    config.updated_at = now_kst_iso()
    payload = config.to_firestore()
    save_json_file(CONFIG_PATH, payload)

    client, status = firestore_client()
    firestore_ok = False
    firestore_error = status.get("error", "")
    if client:
        try:
            ref = client.collection(COLLECTION_CONFIG).document(CONFIG_DOC_ID)
            ref.set(payload, merge=True)
            firestore_ok = True
            firestore_error = ""
        except Exception as exc:
            firestore_error = f"{type(exc).__name__}:{exc}"

    return persist_result(local_ok=True, firestore_ok=firestore_ok, firestore_error=firestore_error)


def is_initialized() -> bool:
    return load_config().initialized
