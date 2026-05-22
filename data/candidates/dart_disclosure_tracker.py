"""DART rcept_no 기반 새 중요공시 판별 (AI 호출 없음)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from data.dart_client import (
    DART_IMPORTANT_KEYWORDS,
    fetch_important_disclosure_items,
    is_dart_configured,
    is_important_disclosure,
)

logger = logging.getLogger("candidates.dart_tracker")

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "data" / "candidates" / "dart_rcept_state.json"
VERSION = "dart_rcept_v1"


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"version": VERSION, "by_ticker": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("by_ticker", {})
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"version": VERSION, "by_ticker": {}}


def _save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["version"] = VERSION
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_new_important_disclosures(
    ticker: str,
    *,
    days: int = 14,
    persist: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    """
    새 중요공시만 반환. (items, had_new).
    persist=True 이면 seen rcept_no 갱신.
    """
    code = str(ticker).zfill(6)
    if not is_dart_configured():
        return [], False

    items = fetch_important_disclosure_items(code, days=days, top_n=10)
    state = _load_state()
    seen: set[str] = set(state.get("by_ticker", {}).get(code, []))
    new_items: list[dict[str, Any]] = []

    for row in items:
        rcept_no = str(row.get("rcept_no") or "").strip()
        if not rcept_no:
            continue
        if rcept_no in seen:
            continue
        report_nm = str(row.get("report_nm") or "")
        if not is_important_disclosure(report_nm):
            continue
        kw = [k for k in DART_IMPORTANT_KEYWORDS if k in report_nm]
        new_items.append({**row, "matched_keywords": kw, "is_new": True})

    if persist:
        all_seen = seen | {str(r.get("rcept_no")) for r in items if r.get("rcept_no")}
        state.setdefault("by_ticker", {})[code] = sorted(all_seen)[-200:]
        _save_state(state)

    return new_items, len(new_items) > 0


def format_dart_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    parts = []
    for row in items[:3]:
        nm = row.get("report_nm", "")
        dt = row.get("rcept_dt", "")
        parts.append(f"{dt} {nm}".strip())
    return "; ".join(parts)
