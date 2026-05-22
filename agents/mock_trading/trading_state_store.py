# -*- coding: utf-8 -*-
"""투자 상태 저장 — Firestore(가능 시) + 로컬 JSON 폴백."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = ROOT / "data" / "mock_trading" / "trading_state.json"
FIRESTORE_COLLECTION = "mock_trading_states"


def _load_local(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_local(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _try_firestore_save(week_id: str, holdings: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import config
        from firebase_client import _init_firebase  # type: ignore
        from firebase_admin import firestore  # type: ignore
    except Exception as exc:
        return {"ok": False, "backend": "none", "error": f"import:{type(exc).__name__}"}

    if not config.FIREBASE_STORAGE_BUCKET:
        return {"ok": False, "backend": "none", "error": "FIREBASE_STORAGE_BUCKET unset"}

    if not _init_firebase():
        return {"ok": False, "backend": "firebase", "error": "firebase init failed"}

    try:
        db = firestore.client()
        doc = {
            "week_id": week_id,
            "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "holdings": holdings,
        }
        db.collection(FIRESTORE_COLLECTION).document(week_id).set(doc, merge=True)
        return {"ok": True, "backend": "firestore", "error": ""}
    except Exception as exc:
        return {"ok": False, "backend": "firestore", "error": str(exc)}


def _try_firestore_load(week_id: str) -> dict[str, Any] | None:
    try:
        import config
        from firebase_client import _init_firebase  # type: ignore
        from firebase_admin import firestore  # type: ignore
    except Exception:
        return None

    if not config.FIREBASE_STORAGE_BUCKET or not _init_firebase():
        return None

    try:
        db = firestore.client()
        snap = db.collection(FIRESTORE_COLLECTION).document(week_id).get()
        if snap.exists:
            data = snap.to_dict() or {}
            if isinstance(data.get("holdings"), list):
                return data
    except Exception:
        return None
    return None


def load_trading_state(
    week_id: str,
    *,
    path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    remote = _try_firestore_load(week_id)
    if remote:
        remote.setdefault("persist_backend", "firestore")
        _save_local(path, remote)
        return remote

    local = _load_local(path)
    if local.get("week_id") == week_id:
        local.setdefault("persist_backend", "local_json")
        return local
    return {"week_id": week_id, "holdings": [], "persist_backend": "none"}


def save_trading_state(
    week_id: str,
    holdings: list[dict[str, Any]],
    *,
    path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    now = datetime.now(KST).isoformat(timespec="seconds")
    doc = {"week_id": week_id, "updated_at": now, "holdings": holdings}
    _save_local(path, doc)

    fb = _try_firestore_save(week_id, holdings)
    doc["persist_backend"] = fb.get("backend") if fb.get("ok") else "local_json"
    doc["firebase"] = fb
    return doc
