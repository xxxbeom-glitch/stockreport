# -*- coding: utf-8 -*-
"""에이전트 전 기간 누적 성과 — 현재 평가 기준 (실현손익·종료 없음)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.agent_catalog import (
    AGENT_DISPLAY_BY_KEY,
    CANONICAL_AGENT_KEYS,
    iter_canonical_specs,
)
from agents.mock_trading.virtual_positions_store import list_positions

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "data" / "mock_trading"
PERF_PATH = MOCK_DIR / "agent_performance.json"

COLLECTION = "agentPerformance"


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _empty_perf(agent_key: str) -> dict[str, Any]:
    return {
        "agentId": agent_key,
        "agentName": AGENT_DISPLAY_BY_KEY.get(agent_key, agent_key),
        "totalTrades": 0,
        "totalInvestedAmount": 0,
        "totalEvaluationAmount": 0,
        "totalProfitLoss": 0,
        "cumulativeReturnRate": 0.0,
        "updatedAt": _now_iso(),
    }


def _position_amounts(pos: dict[str, Any]) -> tuple[int, int, int]:
    """invested, evaluation, profit_loss (현재 평가)."""
    invested = int(pos.get("investedAmount") or 0)
    if invested <= 0:
        buy = int(pos.get("buyPrice") or 0)
        qty = max(1, int(pos.get("quantity") or 1))
        invested = buy * qty
    eval_amount = int(pos.get("currentPrice") or pos.get("buyPrice") or 0) * max(
        1, int(pos.get("quantity") or 1)
    )
    if pos.get("currentProfitLoss") is not None:
        pl = int(pos["currentProfitLoss"])
    else:
        pl = eval_amount - invested
    return invested, eval_amount, pl


def compute_all_agent_performance(
    positions: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """가상매수된 종목의 현재 평가손익을 에이전트별 누적."""
    positions = positions if positions is not None else list_positions()
    perf: dict[str, dict[str, Any]] = {key: _empty_perf(key) for key in CANONICAL_AGENT_KEYS}

    for pos in positions:
        keys = list(pos.get("executionAgentKeys") or pos.get("agentKeys") or [])
        if not keys:
            continue
        invested, evaluation, pl = _position_amounts(pos)
        if invested <= 0:
            continue

        for agent_key in keys:
            if agent_key not in perf:
                perf[agent_key] = _empty_perf(agent_key)
            row = perf[agent_key]
            row["totalTrades"] += 1
            row["totalInvestedAmount"] += invested
            row["totalEvaluationAmount"] += evaluation
            row["totalProfitLoss"] += pl

    for row in perf.values():
        inv = int(row["totalInvestedAmount"])
        row["cumulativeReturnRate"] = (
            round(float(row["totalProfitLoss"]) / inv * 100.0, 2) if inv > 0 else 0.0
        )
        row["updatedAt"] = _now_iso()

    return perf


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


def _save_mirror_all(perf_map: dict[str, dict[str, Any]]) -> None:
    payload = {
        "agents": perf_map,
        "updatedAt": _now_iso(),
        "persist_backend": "local_json",
    }
    PERF_PATH.parent.mkdir(parents=True, exist_ok=True)
    PERF_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_all_agent_performance() -> dict[str, dict[str, Any]]:
    return compute_all_agent_performance()


def save_all_agent_performance(
    perf_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    perf_map = perf_map or compute_all_agent_performance()
    _save_mirror_all(perf_map)

    db, meta = _firestore_client()
    result: dict[str, Any] = {
        "ok": True,
        "persist_backend": "local_json",
        "count": len(perf_map),
        "firebase": meta,
    }
    if not db:
        return result

    try:
        for agent_key, doc in perf_map.items():
            payload = {k: v for k, v in doc.items() if k not in ("activeTrades", "realizedTrades")}
            payload["agentId"] = agent_key
            payload["agentName"] = AGENT_DISPLAY_BY_KEY.get(agent_key, agent_key)
            payload["updatedAt"] = _now_iso()
            db.collection(COLLECTION).document(agent_key).set(payload, merge=True)
        result["persist_backend"] = "firestore"
        result["firestore_path"] = COLLECTION
        result["firebase"] = {"ok": True}
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
    return result


def recompute_and_persist() -> dict[str, Any]:
    perf = compute_all_agent_performance()
    save_result = save_all_agent_performance(perf)
    return {"ok": save_result.get("ok", True), "agents": perf, "persist": save_result}


def agent_panel_rows(perf_map: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    perf_map = perf_map or load_all_agent_performance()
    rows: list[dict[str, Any]] = []
    for spec in iter_canonical_specs():
        doc = perf_map.get(spec.agent_key) or _empty_perf(spec.agent_key)
        rows.append(
            {
                "agent_key": spec.agent_key,
                "name": spec.display_name,
                "model_id": "",
                "perspective": spec.perspective,
                "cumulative_return_pct": float(doc.get("cumulativeReturnRate") or 0.0),
                "pick_count": int(doc.get("totalTrades") or 0),
                "total_trades": int(doc.get("totalTrades") or 0),
                "total_invested_amount": int(doc.get("totalInvestedAmount") or 0),
                "total_evaluation_amount": int(doc.get("totalEvaluationAmount") or 0),
                "total_profit_loss": int(doc.get("totalProfitLoss") or 0),
            }
        )
    return rows
