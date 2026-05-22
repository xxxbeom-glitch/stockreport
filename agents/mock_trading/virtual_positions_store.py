# -*- coding: utf-8 -*-
"""전 주차 누적 가상매수 포지션 — 매도·익절·종료 없이 계속 관찰."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.agent_catalog import (
    agent_keys_to_names,
    normalize_agent_keys,
    normalize_agent_names,
)
from agents.mock_trading.milestone_tracker import apply_price_observation
from agents.mock_trading.position_schema import (
    find_position,
    find_position_index,
    normalize_position,
    position_id_for_ticker,
)

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "data" / "mock_trading"
LEDGER_PATH = MOCK_DIR / "virtual_positions.json"

COLLECTION = "virtualPositions"
DOC_ID = "ledger"

_LEGACY_EXIT_KEYS = frozenset(
    {
        "takeProfitAt",
        "take_profit_at",
        "realizedReturnPct",
        "realizedProfitLoss",
        "realizedEvalAmount",
        "soldAt",
        "exitPrice",
        "finalReturnRate",
        "realizedAt",
        "stopLossPrice",
        "stop_loss_price",
    }
)


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"positions": [], "updatedAt": ""}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_mirror(ledger: dict[str, Any]) -> None:
    ledger["updatedAt"] = _now_iso()
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _firestore_client():
    try:
        import config
        from firebase_client import _init_firebase  # type: ignore
        from firebase_admin import firestore  # type: ignore
    except Exception as exc:
        return None, {"ok": False, "error": f"import:{type(exc).__name__}"}

    if not config.FIREBASE_STORAGE_BUCKET or not _init_firebase():
        return None, {"ok": False, "error": "firebase unavailable"}
    return firestore.client(), {"ok": True, "error": ""}


def _sanitize_position(row: dict[str, Any]) -> dict[str, Any]:
    """종료·익절 레거시 제거 + 신규 스키마 정규화."""
    clean = {k: v for k, v in row.items() if k not in _LEGACY_EXIT_KEYS}
    clean = normalize_position(clean)
    qty = max(1, int(clean.get("quantity") or 1))
    buy = int(clean.get("buyPrice") or 0)
    clean["quantity"] = qty
    if buy > 0 and not clean.get("investedAmount"):
        clean["investedAmount"] = buy * qty
    agents = normalize_agent_names(
        list(clean.get("recommendedAgents") or clean.get("agentNames") or [])
    )
    clean["recommendedAgents"] = agents
    clean["agentNames"] = agents
    cur = int(clean.get("currentPrice") or buy)
    if buy > 0:
        apply_price_observation(clean, cur)
    return clean


def position_id(week_id: str, ticker: str) -> str:
    """레거시 호환 — 신규 포지션은 ticker 단일 ID."""
    if week_id:
        return f"{week_id}_{str(ticker).zfill(6)}"
    return position_id_for_ticker(ticker)


def load_ledger() -> dict[str, Any]:
    db, meta = _firestore_client()
    if db:
        try:
            snap = db.collection(COLLECTION).document(DOC_ID).get()
            if snap.exists:
                data = snap.to_dict() or {}
                data.setdefault("positions", [])
                data["positions"] = [_sanitize_position(p) for p in data["positions"]]
                data["persist_backend"] = "firestore"
                _save_mirror(data)
                return data
        except Exception as exc:
            meta = {"ok": False, "error": str(exc)}

    local = _load_json(LEDGER_PATH)
    local.setdefault("positions", [])
    local["positions"] = [_sanitize_position(p) for p in local["positions"]]
    local.setdefault("persist_backend", "local_json")
    local["firebase"] = meta
    return local


def save_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    ledger = dict(ledger)
    ledger["positions"] = [_sanitize_position(p) for p in ledger.get("positions") or []]
    ledger["updatedAt"] = _now_iso()
    _save_mirror(ledger)

    db, meta = _firestore_client()
    result: dict[str, Any] = {"ok": True, "persist_backend": "local_json", "firebase": meta}
    if not db:
        return result

    try:
        payload = {
            "positions": ledger.get("positions") or [],
            "updatedAt": ledger["updatedAt"],
        }
        db.collection(COLLECTION).document(DOC_ID).set(payload, merge=True)
        result["persist_backend"] = "firestore"
        result["firestore_path"] = f"{COLLECTION}/{DOC_ID}"
        result["firebase"] = {"ok": True}
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        result["firebase"] = {"ok": False, "error": str(exc)}
    return result


def list_positions() -> list[dict[str, Any]]:
    return list(load_ledger().get("positions") or [])


def get_position_by_ticker(ticker: str) -> dict[str, Any] | None:
    return find_position(list_positions(), ticker)


def get_position(week_id: str, ticker: str) -> dict[str, Any] | None:
    row = get_position_by_ticker(ticker)
    if row:
        return row
    pid = position_id(week_id, ticker)
    for r in list_positions():
        if r.get("positionId") == pid:
            return r
    return None


def upsert_position_from_virtual_buy(
    week_id: str,
    record: dict[str, Any],
    *,
    current_price: int | None = None,
) -> dict[str, Any]:
    """레거시 주간 virtualBuys → ledger (신규는 virtual_buy_service 사용)."""
    ticker = str(record.get("ticker", "")).zfill(6)
    if not ticker:
        return {"ok": False, "error": "ticker required"}

    from agents.mock_trading.virtual_buy_service import (
        append_recommendation_only,
        has_holding,
        register_execution,
    )

    if has_holding(ticker):
        return append_recommendation_only(
            ticker,
            agent_keys=list(record.get("agentKeys") or record.get("agent_keys") or []),
            agent_names=list(
                record.get("recommendedAgents")
                or record.get("recommending_agents")
                or []
            ),
            entry_type=str(record.get("entryType") or record.get("entry_type") or "LEGACY"),
            trigger_type=str(record.get("triggerType") or record.get("trigger_type") or "REGULAR"),
            trigger_reason=list(record.get("triggerReason") or record.get("trigger_reason") or []),
            signal_at=str(record.get("boughtAt") or record.get("bought_at") or ""),
        )

    buy_price = int(record.get("buyPrice") or record.get("buy_price") or record.get("buy_amount") or 0)
    bought_at = str(record.get("boughtAt") or record.get("bought_at") or _now_iso())
    cur = int(current_price if current_price is not None else (record.get("currentPrice") or buy_price))
    if buy_price > 0:
        return register_execution(
            ticker=ticker,
            name=str(record.get("name") or ""),
            execution_price=buy_price,
            execution_at=bought_at,
            execution_market=str(record.get("executionMarket") or "KRX_REGULAR"),
            fallback_execution=bool(record.get("fallbackExecution")),
            entry_type=str(record.get("entryType") or "LEGACY"),
            trigger_type=str(record.get("triggerType") or "REGULAR"),
            has_weekend_risk=bool(record.get("hasWeekendRisk")),
            trigger_reason=list(record.get("triggerReason") or []),
            agent_keys=list(record.get("agentKeys") or record.get("agent_keys") or []),
            agent_names=list(record.get("recommendedAgents") or record.get("recommending_agents") or []),
            first_signal_at=bought_at,
            signal_price=buy_price,
            quantity=max(1, int(record.get("quantity") or 1)),
            judgment_run_id=str(record.get("judgmentRunId") or week_id),
        )

    return {"ok": False, "error": "buy_price required for legacy import"}


def refresh_position_prices(
    prices: dict[str, int],
    *,
    week_id: str | None = None,
) -> dict[str, Any]:
    """현재가·최고/최저·마일스톤 갱신 (매도·종료 없음)."""
    ledger = load_ledger()
    updated = 0
    for pos in ledger.get("positions") or []:
        if week_id and str(pos.get("weekId")) != week_id:
            continue
        ticker = str(pos.get("ticker", "")).zfill(6)
        if ticker not in prices:
            continue
        apply_price_observation(pos, int(prices[ticker]))
        updated += 1
    save_ledger(ledger)
    return {"ok": True, "updated": updated}


def import_from_week_doc(week_id: str, week_doc: dict[str, Any]) -> int:
    """weeklyRecommendations virtualBuys → ledger (익절 목록은 무시)."""
    count = 0
    for buy in week_doc.get("virtualBuys") or []:
        if isinstance(buy, dict):
            upsert_position_from_virtual_buy(week_id, buy)
            count += 1
    return count


def sync_ledger_from_all_stored_weeks() -> int:
    """저장된 모든 주간 문서의 virtualBuys → ledger (기존 기록 유지·갱신)."""
    from agents.mock_trading.weekly_recommendations_store import (
        MIRROR_DIR,
        load_weekly_recommendations,
    )

    week_ids: set[str] = set()
    if MIRROR_DIR.is_dir():
        for path in MIRROR_DIR.glob("weekly_*.json"):
            stem = path.stem
            if stem.startswith("weekly_"):
                week_ids.add(stem[len("weekly_") :])
    merged_path = MOCK_DIR / "merged_recommendations.json"
    if merged_path.is_file():
        merged = _load_json(merged_path)
        wid = str(merged.get("week_id") or "").strip()
        if wid:
            week_ids.add(wid)

    total = 0
    for week_id in sorted(week_ids):
        doc = load_weekly_recommendations(week_id)
        if doc:
            total += import_from_week_doc(week_id, doc)
    return total


def positions_by_week(week_id: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for pos in list_positions():
        if str(pos.get("weekId")) == week_id:
            out[str(pos.get("ticker", "")).zfill(6)] = pos
    return out
