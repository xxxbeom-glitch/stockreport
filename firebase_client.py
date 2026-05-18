"""Firebase storage + lightweight history helpers.

This module is intentionally defensive:
- Works with Firebase Admin SDK when available.
- Falls back to local JSONL history when unavailable.
- Supports both legacy direct arguments and payload-style calls.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import config

load_dotenv()

try:
    import firebase_admin  # type: ignore
    from firebase_admin import credentials, firestore, storage  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    firebase_admin = None  # type: ignore
    credentials = None  # type: ignore
    firestore = None  # type: ignore
    storage = None  # type: ignore


PROJECT_ID = "cole-c3f96"
DEFAULT_BUCKET = "cole-c3f96.firebasestorage.app"
LOCAL_HISTORY_PATH = Path("outputs/report_history.jsonl")
DEFAULT_LOCAL_KEY = Path("D:/project/stockreport/cole-c3f96-firebase-adminsdk-fbsvc-be477d7ab7.json")
_INIT_STATE: dict[str, Any] = {"ok": False, "error": "", "source": ""}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class _InitPayload:
    cred: Any
    source: str


def _normalize_inputs(
    payload: dict[str, Any] | None,
    report_data: dict[str, Any] | None,
    file_path: str | None,
    report_type: str | None,
    filename: str | None,
) -> tuple[dict[str, Any], str, str]:
    """Normalize both payload-style and direct-style inputs."""
    source = payload or {}
    merged_report_data = report_data or source.get("report_data") or {}
    merged_file_path = file_path or source.get("file_path") or ""
    merged_report_type = report_type or source.get("report_type") or merged_report_data.get("report_type", "unknown")
    merged_filename = filename or source.get("filename")
    if not merged_filename and merged_file_path:
        merged_filename = Path(merged_file_path).name
    if not merged_filename:
        merged_filename = f"{datetime.now().strftime('%y%m%d')}_{merged_report_type}.json"
    return merged_report_data, merged_file_path, str(merged_filename)


def _append_local_record(record: dict[str, Any]) -> None:
    LOCAL_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_local_records() -> list[dict[str, Any]]:
    if not LOCAL_HISTORY_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in LOCAL_HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _prune_local_history(retention_days: int) -> None:
    rows = _read_local_records()
    if not rows:
        return
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    kept: list[dict[str, Any]] = []
    for row in rows:
        ts = row.get("created_at")
        if not ts:
            kept.append(row)
            continue
        try:
            created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if created >= cutoff:
                kept.append(row)
        except Exception:
            kept.append(row)
    LOCAL_HISTORY_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in kept) + ("\n" if kept else ""),
        encoding="utf-8",
    )


def _resolve_key_path() -> Path | None:
    """Resolve local service-account path robustly."""
    candidates = [
        Path(config.FIREBASE_KEY_PATH),
        Path(config.PROJECT_ROOT) / config.FIREBASE_KEY_PATH,
        DEFAULT_LOCAL_KEY,
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate.resolve()
        except Exception:
            continue
    return None


def _resolve_credentials() -> _InitPayload | None:
    """Resolve credentials from env JSON first, then local key file."""
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
    if service_account_json:
        try:
            info = json.loads(service_account_json)
            return _InitPayload(cred=credentials.Certificate(info), source="FIREBASE_SERVICE_ACCOUNT")
        except Exception as exc:
            _INIT_STATE["error"] = f"invalid FIREBASE_SERVICE_ACCOUNT json: {exc}"
            return None

    key_path = _resolve_key_path()
    if key_path is None:
        _INIT_STATE["error"] = "service account key file not found"
        return None
    try:
        return _InitPayload(cred=credentials.Certificate(str(key_path)), source=str(key_path))
    except Exception as exc:
        _INIT_STATE["error"] = f"invalid key file: {exc}"
        return None


def _init_firebase() -> bool:
    """Initialize Firebase app once if SDK and credentials are available."""
    if not firebase_admin or not credentials:
        _INIT_STATE.update({"ok": False, "error": "firebase_admin not installed", "source": ""})
        return False
    try:
        firebase_admin.get_app()
        _INIT_STATE.update({"ok": True, "error": "", "source": _INIT_STATE.get("source", "existing_app")})
        return True
    except Exception:
        pass

    bucket_name = config.FIREBASE_STORAGE_BUCKET or DEFAULT_BUCKET
    init_payload = _resolve_credentials()
    if init_payload is None:
        _INIT_STATE["ok"] = False
        return False

    try:
        firebase_admin.initialize_app(
            init_payload.cred,
            {
                "storageBucket": bucket_name,
                "projectId": PROJECT_ID,
            },
        )
        _INIT_STATE.update({"ok": True, "error": "", "source": init_payload.source})
        return True
    except Exception as exc:
        _INIT_STATE.update({"ok": False, "error": str(exc), "source": init_payload.source})
        return False


def _upload_to_storage(file_path: str, filename: str) -> str:
    """Upload HTML report to Firebase Storage and return public URL."""
    if not file_path:
        return ""
    path_obj = Path(file_path)
    if not path_obj.exists():
        return ""
    if not _init_firebase() or not storage:
        return ""

    try:
        bucket = storage.bucket()
        object_name = f"reports/{datetime.now().strftime('%Y/%m/%d')}/{filename}"
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(path_obj), content_type="text/html")
        # Public URL or gs path fallback.
        try:
            blob.make_public()
            return blob.public_url
        except Exception:
            # Many buckets block public ACL (UBLA). Return gs path at least.
            return f"gs://{bucket.name}/{object_name}"
    except Exception:
        return ""


def save_report(
    payload: dict[str, Any] | None = None,
    report_data: dict[str, Any] | None = None,
    file_path: str | None = None,
    report_type: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Save report metadata and optionally upload artifact.

    Returns a dict with `ok`, `url`, and `record`.
    """
    data, resolved_file_path, resolved_filename = _normalize_inputs(
        payload, report_data, file_path, report_type, filename
    )
    resolved_type = payload.get("report_type") if payload else None
    if not resolved_type:
        resolved_type = report_type or data.get("report_type", "unknown")

    uploaded_url = _upload_to_storage(resolved_file_path, resolved_filename)
    record = {
        "created_at": _now_iso(),
        "report_type": resolved_type,
        "file_path": resolved_file_path,
        "filename": resolved_filename,
        "url": uploaded_url,
        "summary": data.get("one_line_summary", ""),
        "report_data": data,
    }

    # Firestore optional write.
    firestore_saved = False
    firestore_error = ""
    init_error = ""
    if _init_firebase() and firestore:
        try:
            db = firestore.client()
            db.collection("reports").add(record)
            firestore_saved = True
        except Exception as exc:
            firestore_saved = False
            firestore_error = str(exc)
    else:
        init_error = str(_INIT_STATE.get("error", "firebase init failed"))

    _append_local_record(record)
    _prune_local_history(getattr(config, "RETENTION_DAYS", 14))
    return {
        "ok": True,
        "url": uploaded_url,
        "record": record,
        "firestore_saved": firestore_saved,
        "firebase_init_ok": bool(_INIT_STATE.get("ok")),
        "firebase_init_source": str(_INIT_STATE.get("source", "")),
        "firebase_init_error": init_error,
        "firestore_error": firestore_error,
    }


def get_recent(days: int = 7) -> list[dict[str, Any]]:
    """Get recent report_data entries, preferring Firestore when available."""
    cutoff = datetime.now(UTC) - timedelta(days=max(days, 1))

    # Try Firestore first.
    if _init_firebase() and firestore:
        try:
            db = firestore.client()
            docs = db.collection("reports").stream()
            out: list[dict[str, Any]] = []
            for doc in docs:
                item = doc.to_dict() or {}
                created_at = item.get("created_at")
                if created_at:
                    try:
                        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                        if created < cutoff:
                            continue
                    except Exception:
                        pass
                report_data = item.get("report_data")
                if isinstance(report_data, dict):
                    out.append(report_data)
            if out:
                return out
        except Exception:
            pass

    # Fallback to local history.
    rows = _read_local_records()
    recent: list[dict[str, Any]] = []
    for row in rows:
        created_at = row.get("created_at")
        if created_at:
            try:
                created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if created < cutoff:
                    continue
            except Exception:
                pass
        report_data = row.get("report_data")
        if isinstance(report_data, dict):
            recent.append(report_data)
    return recent
