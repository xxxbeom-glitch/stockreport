"""Per-trading-day KIS enrich checkpoint (ticker cursor) for REPLAY resume."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from src.trading.competition.models import now_kst_iso
from src.trading.competition.replay.campaign_resume import camp_dir, load_checkpoint, save_checkpoint

PHASE_OHLCV = "ohlcv_enrich"
PHASE_RISK = "risk_enrich"


def _records_path(campaign_id: str, trading_date: str) -> Path:
    d = camp_dir(campaign_id) / "day_progress"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{trading_date}_records.json"


def is_record_ohlcv_enriched(rec: dict[str, Any], trading_date: str) -> bool:
    """True when this ticker already has as-of OHLCV for trading_date (skip re-fetch)."""
    if int(rec.get("current_price_krw") or 0) <= 0:
        return False
    sources = list(rec.get("data_sources") or [])
    if "kis_historical" in sources or "replay_ohlcv" in sources:
        return True
    return bool(rec.get("_ohlcv_enriched_date") == trading_date)


def is_record_risk_enriched(rec: dict[str, Any]) -> bool:
    return str(rec.get("risk_check_status") or "") == "verified"


def load_day_progress(campaign_id: str) -> dict[str, Any] | None:
    ck = load_checkpoint(campaign_id)
    dip = ck.get("day_in_progress")
    if not isinstance(dip, dict) or not dip.get("trading_date"):
        return None
    return dict(dip)


def save_day_progress(
    campaign_id: str,
    progress: dict[str, Any],
    *,
    records: list[dict[str, Any]] | None = None,
) -> None:
    if records is not None:
        td = str(progress.get("trading_date") or "")
        if td:
            path = _records_path(campaign_id, td)
            path.write_text(
                json.dumps({"trading_date": td, "records": records}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            progress["records_file"] = path.name
    progress["last_checkpoint_at"] = now_kst_iso()
    ck = load_checkpoint(campaign_id)
    ck["day_in_progress"] = progress
    save_checkpoint(campaign_id, ck)


def clear_day_progress(campaign_id: str, *, trading_date: str | None = None) -> None:
    ck = load_checkpoint(campaign_id)
    dip = ck.get("day_in_progress")
    if trading_date and isinstance(dip, dict) and dip.get("trading_date") != trading_date:
        return
    ck.pop("day_in_progress", None)
    save_checkpoint(campaign_id, ck)
    if trading_date:
        path = _records_path(campaign_id, trading_date)
        if path.is_file():
            path.unlink()


def load_partial_day_records(campaign_id: str, trading_date: str) -> list[dict[str, Any]] | None:
    path = _records_path(campaign_id, trading_date)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("records")
    if not isinstance(rows, list):
        return None
    return copy.deepcopy(rows)


def merge_master_with_partial(
    master: list[dict[str, Any]],
    partial: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not partial:
        return [dict(r) for r in master]
    by_ticker = {str(r.get("ticker", "")).zfill(6): dict(r) for r in master}
    for row in partial:
        t = str(row.get("ticker", "")).zfill(6)
        if t in by_ticker:
            by_ticker[t].update(row)
        else:
            by_ticker[t] = dict(row)
    return list(by_ticker.values())


def trading_date_in_progress(campaign_id: str, trading_date: str) -> bool:
    dip = load_day_progress(campaign_id)
    return bool(dip and str(dip.get("trading_date")) == trading_date)
