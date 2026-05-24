"""Asset snapshots for dashboard chart."""

from __future__ import annotations

import json
import uuid
from typing import Any

from src.trading.competition.constants import TEAM_IDS
from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.accounts import load_all_accounts
from src.trading.competition.storage.base import ROOT, append_jsonl, read_jsonl, save_json_file
from src.trading.competition.storage.positions import load_all_positions

SNAPSHOTS_PATH = ROOT / "data" / "competition" / "snapshots.jsonl"
SNAPSHOT_INDEX_PATH = ROOT / "data" / "competition" / "snapshot_index.json"


def capture_team_snapshots(*, kospi_return_pct: float | None = None) -> list[dict[str, Any]]:
    accounts = load_all_accounts()
    positions = load_all_positions()
    ts = now_kst_iso()
    rows: list[dict[str, Any]] = []

    for tid in TEAM_IDS:
        acc = accounts.get(tid)
        tp = positions.get(tid)
        pos_val = 0
        if tp:
            pos_val = int(
                sum(p.current_price_krw * p.quantity for p in tp.positions if p.quantity > 0)
            )
        cash = acc.cash_krw if acc else 0
        total = acc.total_assets_krw if acc else cash + pos_val
        row = {
            "snapshot_id": f"snap_{uuid.uuid4().hex[:10]}",
            "team_id": tid,
            "total_assets_krw": total,
            "cash_krw": cash,
            "positions_value_krw": pos_val,
            "kospi_return_pct": kospi_return_pct,
            "captured_at": ts,
        }
        append_jsonl(SNAPSHOTS_PATH, row)
        rows.append(row)

    index = load_snapshot_index()
    index.setdefault("captures", []).append({"captured_at": ts, "team_count": len(rows)})
    index["updated_at"] = ts
    save_json_file(SNAPSHOT_INDEX_PATH, index)
    return rows


def load_snapshots() -> list[dict[str, Any]]:
    return read_jsonl(SNAPSHOTS_PATH)


def load_snapshot_index() -> dict[str, Any]:
    if not SNAPSHOT_INDEX_PATH.is_file():
        return {"captures": [], "updated_at": ""}
    return json.loads(SNAPSHOT_INDEX_PATH.read_text(encoding="utf-8"))
