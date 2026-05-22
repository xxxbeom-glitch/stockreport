# -*- coding: utf-8 -*-
"""주간 추천 Firestore 저장 — weeklyRecommendations/{week_id} (문서 ID = week_id, 덮어쓰기)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "data" / "mock_trading"
MERGED_PATH = MOCK_DIR / "merged_recommendations.json"
WEEKLY_PATH = MOCK_DIR / "weekly_recommendations.json"
MIRROR_DIR = MOCK_DIR / "firebase_mirror"

COLLECTION = "weeklyRecommendations"


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_path(week_id: str) -> Path:
    safe = week_id.replace("/", "_")
    return MIRROR_DIR / f"weekly_{safe}.json"


def _save_mirror(week_id: str, doc: dict[str, Any]) -> None:
    path = _mirror_path(week_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_mirror(week_id: str) -> dict[str, Any] | None:
    path = _mirror_path(week_id)
    if not path.is_file():
        return None
    return _load_json(path)


def _firestore_client():
    try:
        import config
        from firebase_client import _init_firebase  # type: ignore
        from firebase_admin import firestore  # type: ignore
    except Exception as exc:
        return None, {"ok": False, "error": f"import:{type(exc).__name__}"}

    if not config.FIREBASE_STORAGE_BUCKET:
        return None, {"ok": False, "error": "FIREBASE_STORAGE_BUCKET unset"}
    if not _init_firebase():
        return None, {"ok": False, "error": "firebase init failed"}
    return firestore.client(), {"ok": True, "error": ""}


def _strip_stop_loss_card(card: dict[str, Any]) -> dict[str, Any]:
    out = dict(card)
    out.pop("stop_loss_price", None)
    out.pop("stopLossPrice", None)
    return out


def _strip_stop_loss_agents(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for agent in agents:
        row = dict(agent)
        recs = []
        for rec in row.get("recommendations") or []:
            if isinstance(rec, dict):
                recs.append(_strip_stop_loss_card(rec))
        row["recommendations"] = recs
        cleaned.append(row)
    return cleaned


def build_firestore_doc(
    merged: dict[str, Any],
    weekly: dict[str, Any],
    *,
    preserve_virtual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Firebase 권장 스키마."""
    week_id = str(merged.get("week_id") or weekly.get("week_id") or "")
    summary = weekly.get("universe_summary") or {}
    cards = [_strip_stop_loss_card(c) for c in (merged.get("merged_cards") or [])]
    prev = preserve_virtual or {}

    return {
        "weekId": week_id,
        "generatedAt": merged.get("generated_at") or weekly.get("generated_at") or _now_iso(),
        "mergedRecommendations": cards,
        "agentRecommendations": _strip_stop_loss_agents(weekly.get("agents") or []),
        "grokValidation": weekly.get("grok_validation") or [],
        "sourceCandidateCount": int(
            summary.get("ai_input_candidate_count") or summary.get("final_candidate_count") or 76
        ),
        "uniqueRecommendationCount": int(
            merged.get("ticker_count") or len(cards)
        ),
        "status": "generated",
        "mode": merged.get("mode") or weekly.get("mode") or "",
        "inputSource": weekly.get("input_source") or "",
        "virtualBuys": list(prev.get("virtualBuys") or []),
        "virtualTakeProfits": list(prev.get("virtualTakeProfits") or []),
        "updatedAt": _now_iso(),
    }


def firestore_doc_to_local(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Firestore 문서 → trading_web_sync용 merged/weekly dict."""
    week_id = doc.get("weekId") or doc.get("week_id") or ""
    merged = {
        "week_id": week_id,
        "generated_at": doc.get("generatedAt") or doc.get("generated_at"),
        "merged_cards": doc.get("mergedRecommendations") or doc.get("merged_cards") or [],
        "ticker_count": doc.get("uniqueRecommendationCount")
        or len(doc.get("mergedRecommendations") or []),
        "mode": doc.get("mode"),
    }
    weekly = {
        "week_id": week_id,
        "generated_at": doc.get("generatedAt") or doc.get("generated_at"),
        "agents": doc.get("agentRecommendations") or doc.get("agents") or [],
        "grok_validation": doc.get("grokValidation") or doc.get("grok_validation") or [],
        "universe_summary": {
            "ai_input_candidate_count": doc.get("sourceCandidateCount"),
        },
        "mode": doc.get("mode"),
        "input_source": doc.get("inputSource"),
    }
    return merged, weekly


def load_weekly_recommendations(week_id: str) -> dict[str, Any] | None:
    """Firestore 우선, 없으면 로컬 mirror."""
    db, meta = _firestore_client()
    if db:
        try:
            snap = db.collection(COLLECTION).document(week_id).get()
            if snap.exists:
                data = snap.to_dict() or {}
                data["persist_backend"] = "firestore"
                data["firestore_path"] = f"{COLLECTION}/{week_id}"
                _save_mirror(week_id, data)
                return data
        except Exception as exc:
            meta = {"ok": False, "error": str(exc)}

    mirror = _load_mirror(week_id)
    if mirror:
        mirror.setdefault("persist_backend", "local_mirror")
        mirror.setdefault("firestore_path", f"{COLLECTION}/{week_id}")
        return mirror

    if MERGED_PATH.is_file() and WEEKLY_PATH.is_file():
        merged = _load_json(MERGED_PATH)
        weekly = _load_json(WEEKLY_PATH)
        if str(merged.get("week_id")) == week_id or str(weekly.get("week_id")) == week_id:
            doc = build_firestore_doc(merged, weekly)
            doc["persist_backend"] = "local_json_files"
            doc["firestore_path"] = f"{COLLECTION}/{week_id}"
            return doc

    return None


def save_weekly_recommendations(
    week_id: str,
    merged: dict[str, Any],
    weekly: dict[str, Any],
) -> dict[str, Any]:
    """동일 week_id 문서를 set()으로 전체 갱신(가상매수 기록은 유지)."""
    existing = load_weekly_recommendations(week_id) or {}
    doc = build_firestore_doc(merged, weekly, preserve_virtual=existing)
    doc["weekId"] = week_id
    _save_mirror(week_id, doc)

    db, meta = _firestore_client()
    result: dict[str, Any] = {
        "ok": False,
        "week_id": week_id,
        "firestore_path": f"{COLLECTION}/{week_id}",
        "unique_count": doc.get("uniqueRecommendationCount"),
        "persist_backend": "local_mirror",
        "firebase": meta,
    }

    if not db:
        result.update(
            {
                "ok": True,
                "error": meta.get("error", "firestore unavailable"),
                "note": "saved_to_local_mirror_only",
            }
        )
        return result

    try:
        db.collection(COLLECTION).document(week_id).set(doc)
        result.update(
            {
                "ok": True,
                "persist_backend": "firestore",
                "firebase": {"ok": True, "error": ""},
            }
        )
    except Exception as exc:
        result["error"] = str(exc)
        result["firebase"] = {"ok": False, "error": str(exc)}
        result["ok"] = False

    return result


def save_weekly_from_local_files(
    week_id: str | None = None,
    *,
    merged_path: Path = MERGED_PATH,
    weekly_path: Path = WEEKLY_PATH,
) -> dict[str, Any]:
    merged = _load_json(merged_path)
    weekly = _load_json(weekly_path)
    wid = week_id or str(merged.get("week_id") or weekly.get("week_id") or "")
    if not wid:
        return {"ok": False, "error": "week_id missing"}
    return save_weekly_recommendations(wid, merged, weekly)


def append_virtual_buy(week_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """가상매수 즉시 저장."""
    return _append_virtual_event(week_id, "virtualBuys", record)


def append_virtual_take_profit(week_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """익절 즉시 저장."""
    return _append_virtual_event(week_id, "virtualTakeProfits", record)


def _append_virtual_event(
    week_id: str, field: str, record: dict[str, Any]
) -> dict[str, Any]:
    doc = load_weekly_recommendations(week_id)
    if not doc:
        return {"ok": False, "error": f"weekly doc not found: {week_id}"}

    rows = list(doc.get(field) or [])
    entry = dict(record)
    entry["savedAt"] = _now_iso()
    rows.append(entry)
    doc[field] = rows
    doc["updatedAt"] = _now_iso()
    _save_mirror(week_id, doc)

    db, meta = _firestore_client()
    if not db:
        return {
            "ok": True,
            "persist_backend": "local_mirror",
            "field": field,
            "count": len(rows),
            "firebase": meta,
        }

    try:
        db.collection(COLLECTION).document(week_id).set(
            {field: rows, "updatedAt": doc["updatedAt"]},
            merge=True,
        )
        return {
            "ok": True,
            "persist_backend": "firestore",
            "field": field,
            "count": len(rows),
            "firestore_path": f"{COLLECTION}/{week_id}",
            "firebase": {"ok": True},
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "field": field}
