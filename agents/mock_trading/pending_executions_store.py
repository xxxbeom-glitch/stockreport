# -*- coding: utf-8 -*-
"""
가상 지정가 주문 이력 — pending_executions.json
체결(FILLED)된 건만 virtual_positions ledger로 이동.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.entry_types import (
    LEGACY_STATUS_PENDING,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PENDING,
)

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "data" / "mock_trading"
QUEUE_PATH = MOCK_DIR / "pending_executions.json"

ACTIVE_STATUSES = frozenset({ORDER_STATUS_PENDING, LEGACY_STATUS_PENDING})


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except ValueError:
        return None


def _load() -> dict[str, Any]:
    if not QUEUE_PATH.is_file():
        return {"items": [], "updatedAt": ""}
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def _save(doc: dict[str, Any]) -> None:
    doc["updatedAt"] = _now_iso()
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_status(raw: str) -> str:
    if raw in (ORDER_STATUS_PENDING, ORDER_STATUS_FILLED, ORDER_STATUS_EXPIRED):
        return raw
    if raw == LEGACY_STATUS_PENDING:
        return ORDER_STATUS_PENDING
    return raw


def list_all_orders() -> list[dict[str, Any]]:
    return list(_load().get("items") or [])


def list_pending(*, include_terminal: bool = False) -> list[dict[str, Any]]:
    items = list_all_orders()
    if include_terminal:
        return items
    return [i for i in items if _normalize_status(str(i.get("status"))) in ACTIVE_STATUSES]


def has_open_order_for_ticker(ticker: str) -> bool:
    code = str(ticker).zfill(6)
    for item in list_pending():
        if str(item.get("ticker") or "").zfill(6) == code:
            return True
    return False


def enqueue_limit_order(payload: dict[str, Any]) -> dict[str, Any]:
    """가상 지정가 주문 생성 (즉시 보유 등록 없음)."""
    ticker = str(payload.get("ticker") or "").zfill(6)
    limit_price = int(payload.get("limit_price") or payload.get("limitPrice") or 0)
    if not ticker:
        return {"ok": False, "error": "ticker required"}
    if limit_price <= 0:
        return {"ok": False, "error": "limit_price required"}
    if has_open_order_for_ticker(ticker):
        return {"ok": False, "error": "duplicate_open_order", "ticker": ticker}

    doc = _load()
    items: list[dict[str, Any]] = list(doc.get("items") or [])
    now = _now_iso()
    row = dict(payload)
    row["ticker"] = ticker
    row["limit_price"] = limit_price
    row.setdefault("order_id", row.get("execution_id") or str(uuid.uuid4()))
    row["execution_id"] = row["order_id"]
    row["status"] = ORDER_STATUS_PENDING
    row["order_created_at"] = now
    row.setdefault("created_at", now)
    row.setdefault("order_market", row.get("execution_market") or "KRX_REGULAR")
    items.append(row)
    doc["items"] = items
    _save(doc)
    return {"ok": True, "order": row}


def update_order(order_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    doc = _load()
    items: list[dict[str, Any]] = list(doc.get("items") or [])
    for i, row in enumerate(items):
        if str(row.get("order_id") or row.get("execution_id")) == order_id:
            items[i] = {**row, **patch, "updated_at": _now_iso()}
            doc["items"] = items
            _save(doc)
            return items[i]
    return None


# 하위 호환 alias
enqueue_execution = enqueue_limit_order
update_execution = update_order


def list_orders_in_session(at: datetime | None = None) -> list[dict[str, Any]]:
    """주문 세션 시작~종료 구간의 대기 주문."""
    at = (at or datetime.now(KST)).astimezone(KST)
    active: list[dict[str, Any]] = []
    for item in list_pending():
        start = _parse_iso(str(item.get("scheduled_at") or ""))
        end = _parse_iso(str(item.get("session_end_at") or ""))
        if not start:
            continue
        if at < start:
            continue
        if end and at > end:
            continue
        active.append(item)
    return active


def list_orders_to_expire(at: datetime | None = None) -> list[dict[str, Any]]:
    """세션 종료 시각이 지났으나 아직 대기 중인 주문."""
    at = (at or datetime.now(KST)).astimezone(KST)
    due: list[dict[str, Any]] = []
    for item in list_pending():
        end = _parse_iso(str(item.get("session_end_at") or ""))
        if end and at >= end:
            due.append(item)
    return due


def list_due_pending(at: datetime | None = None) -> list[dict[str, Any]]:
    """체결 판정 배치용 — 세션 내 활성 + 만료 대상."""
    at = (at or datetime.now(KST)).astimezone(KST)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in list_orders_in_session(at) + list_orders_to_expire(at):
        oid = str(item.get("order_id") or item.get("execution_id") or "")
        if oid and oid not in seen:
            seen.add(oid)
            out.append(item)
    return out


def mark_no_buy_judgment(judgment_run_id: str, *, reason: str = "no_passing_candidates") -> dict[str, Any]:
    return {
        "judgment_run_id": judgment_run_id,
        "outcome": "NO_NEW_BUYS",
        "message": "신규 매수 없음",
        "reason": reason,
        "recorded_at": _now_iso(),
    }
