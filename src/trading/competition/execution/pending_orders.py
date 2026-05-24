"""Pending / partial order store — no cross-session rollover."""

from __future__ import annotations

from typing import Any

from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.base import ensure_local_dir, load_json_file, save_json_file

PENDING_PATH = ensure_local_dir() / "pending_orders.json"


def _load() -> list[dict[str, Any]]:
    return load_json_file(PENDING_PATH, {"orders": []}).get("orders") or []


def _save(orders: list[dict[str, Any]]) -> None:
    save_json_file(PENDING_PATH, {"orders": orders, "updated_at": now_kst_iso()})


def load_pending_orders(*, session_id: str | None = None) -> list[dict[str, Any]]:
    orders = [o for o in _load() if o.get("status") in ("pending", "partial")]
    if session_id:
        orders = [o for o in orders if o.get("session_id") == session_id]
    return orders


def upsert_pending_order(order: dict[str, Any]) -> None:
    orders = _load()
    oid = order.get("order_id")
    orders = [o for o in orders if o.get("order_id") != oid]
    orders.append(order)
    _save(orders)


def expire_pending_orders(session_id: str, *, reason: str = "session_end_expired") -> list[dict[str, Any]]:
    """Expire pending/partial for session — never roll forward (spec §9-2)."""
    orders = _load()
    expired: list[dict[str, Any]] = []
    ts = now_kst_iso()
    for o in orders:
        if o.get("session_id") == session_id and o.get("status") in ("pending", "partial"):
            o = dict(o)
            o["status"] = "expired"
            o["status_reason"] = reason
            o["updated_at"] = ts
            expired.append(o)
    if expired:
        expired_ids = {e["order_id"] for e in expired}
        remaining = [o for o in orders if o.get("order_id") not in expired_ids]
        remaining.extend(expired)
        _save(remaining)
    return expired
