# -*- coding: utf-8 -*-
"""
가상매수 등록 — 종목당 최초 1회만 체결, 재추천은 이력·에이전트만 갱신.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.agent_catalog import (
    agent_keys_to_names,
    normalize_agent_keys,
    normalize_agent_names,
)
from agents.mock_trading.agent_performance_store import recompute_and_persist
from agents.mock_trading.entry_types import DEFAULT_MARKET_LABEL, POSITION_STATUS_HOLDING
from agents.mock_trading.kis_market_watch import fetch_quote, quote_to_int_price
from agents.mock_trading.milestone_tracker import apply_price_observation
from agents.mock_trading.position_schema import (
    find_position,
    find_position_index,
    normalize_position,
    position_id_for_ticker,
)
from agents.mock_trading.virtual_positions_store import load_ledger, save_ledger

KST = ZoneInfo("Asia/Seoul")


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def has_holding(ticker: str) -> bool:
    ledger = load_ledger()
    return find_position(list(ledger.get("positions") or []), ticker) is not None


def append_recommendation_only(
    ticker: str,
    *,
    agent_keys: list[str],
    agent_names: list[str] | None = None,
    entry_type: str,
    trigger_type: str,
    trigger_reason: list[str] | None = None,
    signal_at: str | None = None,
) -> dict[str, Any]:
    """이미 보유 중 — 추가 매수·매수가 변경 없이 추천 이력만 갱신."""
    ledger = load_ledger()
    positions: list[dict[str, Any]] = list(ledger.get("positions") or [])
    idx = find_position_index(positions, ticker)
    if idx is None:
        return {"ok": False, "error": "not_holding", "ticker": str(ticker).zfill(6)}

    row = normalize_position(positions[idx])
    keys = normalize_agent_keys(agent_keys)
    names = normalize_agent_names(agent_names or agent_keys_to_names(keys))

    exec_keys = set(row.get("executionAgentKeys") or [])
    merged_names = list(row.get("recommendedAgents") or [])
    for name in names:
        if name and name not in merged_names:
            merged_names.append(name)

    history = list(row.get("recommendationHistory") or [])
    history.append(
        {
            "at": signal_at or _now_iso(),
            "entry_type": entry_type,
            "trigger_type": trigger_type,
            "agent_keys": keys,
            "agent_names": names,
            "trigger_reason": list(trigger_reason or []),
            "action": "recommendation_only",
        }
    )

    row["recommendedAgents"] = merged_names
    row["agentNames"] = merged_names
    row["recommendationCount"] = int(row.get("recommendationCount") or 1) + 1
    row["recommendationHistory"] = history
    row["executionAgentKeys"] = list(exec_keys)
    row["agentKeys"] = list(exec_keys)

    positions[idx] = row
    ledger["positions"] = positions
    saved = save_ledger(ledger)
    recompute_and_persist()
    return {"ok": True, "action": "recommendation_only", "position": row, "persist": saved}


def register_execution(
    *,
    ticker: str,
    name: str,
    execution_price: int,
    execution_at: str,
    execution_market: str,
    fallback_execution: bool,
    entry_type: str,
    trigger_type: str,
    has_weekend_risk: bool,
    trigger_reason: list[str] | None = None,
    agent_keys: list[str] | None = None,
    agent_names: list[str] | None = None,
    first_signal_at: str | None = None,
    signal_price: int | None = None,
    quantity: int = 1,
    judgment_run_id: str | None = None,
) -> dict[str, Any]:
    """신규 가상매수 체결 — 종목당 1회."""
    code = str(ticker).zfill(6)
    if not code:
        return {"ok": False, "error": "ticker required"}
    if execution_price <= 0:
        return {"ok": False, "error": "execution_price required"}

    ledger = load_ledger()
    positions: list[dict[str, Any]] = list(ledger.get("positions") or [])
    if find_position_index(positions, code) is not None:
        return append_recommendation_only(
            code,
            agent_keys=list(agent_keys or []),
            agent_names=agent_names,
            entry_type=entry_type,
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            signal_at=first_signal_at,
        )

    keys = normalize_agent_keys(list(agent_keys or []))
    names = normalize_agent_names(agent_names or agent_keys_to_names(keys))
    qty = max(1, int(quantity))
    invested = execution_price * qty
    sig_at = first_signal_at or execution_at or _now_iso()
    sig_px = int(signal_price if signal_price is not None else execution_price)

    row: dict[str, Any] = {
        "positionId": position_id_for_ticker(code),
        "ticker": code,
        "name": name,
        "market": DEFAULT_MARKET_LABEL,
        "firstSignalAt": sig_at,
        "signalPrice": sig_px,
        "executionAt": execution_at,
        "executionPrice": execution_price,
        "executionMarket": execution_market,
        "fallbackExecution": bool(fallback_execution),
        "entryType": entry_type,
        "triggerType": trigger_type,
        "hasWeekendRisk": bool(has_weekend_risk),
        "triggerReason": list(trigger_reason or []),
        "boughtAt": execution_at,
        "buyPrice": execution_price,
        "quantity": qty,
        "investedAmount": invested,
        "currentPrice": execution_price,
        "executionAgentKeys": keys,
        "agentKeys": keys,
        "recommendedAgents": names,
        "agentNames": names,
        "recommendationCount": 1,
        "status": POSITION_STATUS_HOLDING,
        "judgmentRunId": judgment_run_id,
        "recommendationHistory": [
            {
                "at": sig_at,
                "entry_type": entry_type,
                "trigger_type": trigger_type,
                "agent_keys": keys,
                "agent_names": names,
                "trigger_reason": list(trigger_reason or []),
                "action": "initial_execution",
            }
        ],
    }
    apply_price_observation(row, execution_price)
    row = normalize_position(row)
    positions.append(row)
    ledger["positions"] = positions
    saved = save_ledger(ledger)
    recompute_and_persist()
    return {"ok": True, "action": "new_execution", "position": row, "persist": saved}


def register_from_pending_item(item: dict[str, Any], *, price: int) -> dict[str, Any]:
    fill_at = str(
        item.get("filled_at")
        or item.get("executed_at")
        or item.get("scheduled_at")
        or _now_iso()
    )
    return register_execution(
        ticker=str(item.get("ticker") or ""),
        name=str(item.get("name") or ""),
        execution_price=price,
        execution_at=fill_at,
        execution_market=str(item.get("execution_market") or "KRX_REGULAR"),
        fallback_execution=bool(item.get("fallback_execution")),
        entry_type=str(item.get("entry_type") or "REGULAR_MON"),
        trigger_type=str(item.get("trigger_type") or "REGULAR"),
        has_weekend_risk=bool(item.get("has_weekend_risk")),
        trigger_reason=list(item.get("trigger_reason") or []),
        agent_keys=list(item.get("agent_keys") or []),
        agent_names=list(item.get("agent_names") or []),
        first_signal_at=str(item.get("first_signal_at") or ""),
        signal_price=int(item.get("signal_price") or 0) or None,
        judgment_run_id=str(item.get("judgment_run_id") or ""),
    )


def signal_price_for_ticker(ticker: str) -> int:
    return quote_to_int_price(fetch_quote(ticker))
