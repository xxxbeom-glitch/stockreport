"""Shared storage utilities for competition app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LOCAL_DIR = ROOT / "data" / "competition"


def ensure_local_dir() -> Path:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_DIR


def load_json_file(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def firestore_client() -> tuple[Any | None, dict[str, Any]]:
    try:
        from firebase_client import _init_firebase  # type: ignore
        from firebase_admin import firestore  # type: ignore

        import config
    except Exception as exc:
        return None, {"ok": False, "error": f"import:{type(exc).__name__}"}

    if not config.FIREBASE_STORAGE_BUCKET or not _init_firebase():
        return None, {"ok": False, "error": "firebase unavailable"}
    return firestore.client(), {"ok": True, "error": ""}


def persist_result(
    *,
    local_ok: bool,
    firestore_ok: bool,
    firestore_error: str = "",
) -> dict[str, Any]:
    if local_ok and firestore_ok:
        backend = "firestore"
    elif local_ok:
        backend = "local_mirror"
    else:
        backend = "failed"
    return {
        "ok": local_ok,
        "persist_backend": backend,
        "firestore_ok": firestore_ok,
        "firestore_error": firestore_error,
    }
