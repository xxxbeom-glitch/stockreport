"""임시 관찰 후보 (kr_watchlist.json 미수정)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from data.kr_market import get_trading_date

ROOT = Path(__file__).resolve().parents[2]
STORE_PATH = ROOT / "data" / "candidates" / "temporary_watch_candidates.json"
DEFAULT_VALID_TRADING_DAYS = 5
VERSION = "temporary_watch_v1"


def _kst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def _iso_from_yyyymmdd(raw: str) -> str:
    s = raw.replace("-", "")[:8]
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return raw


def _add_trading_days(iso_date: str, days: int) -> str:
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    added = 0
    while added < days:
        dt += timedelta(days=1)
        if dt.weekday() < 5:
            added += 1
    return dt.strftime("%Y-%m-%d")


def load_store() -> dict[str, Any]:
    if not STORE_PATH.is_file():
        return {"version": VERSION, "updated_at": None, "candidates": []}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("candidates", [])
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"version": VERSION, "updated_at": None, "candidates": []}


def save_store(data: dict[str, Any]) -> Path:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["version"] = VERSION
    data["updated_at"] = _kst_now().strftime("%Y-%m-%d %H:%M:%S")
    STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return STORE_PATH


def purge_expired(store: dict[str, Any] | None = None) -> dict[str, Any]:
    data = store if store is not None else load_store()
    today = _iso_from_yyyymmdd(get_trading_date())
    kept: list[dict[str, Any]] = []
    for row in data.get("candidates") or []:
        exp = str(row.get("expires_at") or "")
        if exp and exp < today:
            continue
        kept.append(row)
    data["candidates"] = kept
    return data


def list_active_temp_candidates() -> list[dict[str, Any]]:
    data = purge_expired()
    return list(data.get("candidates") or [])


def temp_candidates_as_watchlist_entries() -> list[dict[str, Any]]:
    """오전 스캔용 watchlist 형식 엔트리."""
    out: list[dict[str, Any]] = []
    for row in list_active_temp_candidates():
        ticker = str(row.get("ticker", "")).zfill(6)
        if not ticker:
            continue
        sector = str(row.get("sector_name") or "임시관찰")
        out.append(
            {
                "ticker": ticker,
                "name": row.get("name", ticker),
                "sector_key": "temp_watch",
                "sector_name": sector,
                "sector_order": 99,
                "business": "",
                "selection_reason": row.get("selection_reason", "임시 관찰 후보"),
                "source": "temporary_watch",
            }
        )
    return out


def upsert_candidates(
    rows: list[dict[str, Any]],
    *,
    selected_date: str | None = None,
    valid_trading_days: int = DEFAULT_VALID_TRADING_DAYS,
) -> Path:
    sel = selected_date or _iso_from_yyyymmdd(get_trading_date())
    expires = _add_trading_days(sel, valid_trading_days)
    data = purge_expired()
    by_ticker = {
        str(c.get("ticker", "")).zfill(6): c
        for c in data.get("candidates") or []
        if c.get("ticker")
    }
    for row in rows:
        ticker = str(row.get("ticker", "")).zfill(6)
        if not ticker:
            continue
        entry = {
            "ticker": ticker,
            "name": row.get("name", ""),
            "sector_name": row.get("sector_name", ""),
            "selected_date": sel,
            "expires_at": expires,
            "valid_trading_days": valid_trading_days,
            "vote_result": row.get("vote_result", row.get("vote_summary")),
            "trend_score": row.get("trend_score"),
            "gemini_reason": row.get("gemini_reason", ""),
            "dart_disclosure_summary": row.get("dart_disclosure_summary", ""),
            "grok_issue_summary": row.get("grok_issue_summary", ""),
            "deepseek_final_reason": row.get(
                "deepseek_final_reason", row.get("selection_reason", "")
            ),
            "risk_notes": row.get("risk_notes", ""),
            "aftermarket_priority": bool(row.get("aftermarket_priority", False)),
            "final_status": row.get("final_status", "관찰 후보 등록"),
        }
        by_ticker[ticker] = entry
    data["candidates"] = list(by_ticker.values())
    return save_store(data)
