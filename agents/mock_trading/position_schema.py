# -*- coding: utf-8 -*-
"""포지션 스키마 정규화 — 레거시 weekId 포지션 호환."""

from __future__ import annotations

from typing import Any

from agents.mock_trading.entry_types import DEFAULT_MARKET_LABEL, POSITION_STATUS_HOLDING


def position_id_for_ticker(ticker: str) -> str:
    return str(ticker).zfill(6)


def find_position_index(positions: list[dict[str, Any]], ticker: str) -> int | None:
    code = str(ticker).zfill(6)
    for i, row in enumerate(positions):
        if str(row.get("ticker", "")).zfill(6) == code:
            return i
        pid = str(row.get("positionId") or "")
        if pid.endswith(f"_{code}") or pid == code:
            return i
    return None


def find_position(positions: list[dict[str, Any]], ticker: str) -> dict[str, Any] | None:
    idx = find_position_index(positions, ticker)
    if idx is None:
        return None
    return positions[idx]


def normalize_position(row: dict[str, Any]) -> dict[str, Any]:
    """camelCase + snake_case 병행, ticker 단일 positionId."""
    clean = dict(row)
    ticker = str(clean.get("ticker", "")).zfill(6)
    if ticker:
        clean["ticker"] = ticker
        clean["positionId"] = position_id_for_ticker(ticker)

    exec_price = int(
        clean.get("executionPrice")
        or clean.get("execution_price")
        or clean.get("buyPrice")
        or clean.get("buy_price")
        or 0
    )
    exec_at = (
        clean.get("executionAt")
        or clean.get("execution_at")
        or clean.get("boughtAt")
        or clean.get("bought_at")
    )
    if exec_price > 0:
        clean["buyPrice"] = exec_price
        clean["executionPrice"] = exec_price
    if exec_at:
        clean["boughtAt"] = exec_at
        clean["executionAt"] = exec_at

    clean.setdefault("market", clean.get("market") or DEFAULT_MARKET_LABEL)
    clean.setdefault("status", POSITION_STATUS_HOLDING)
    clean.setdefault("quantity", max(1, int(clean.get("quantity") or 1)))

    keys = list(clean.get("executionAgentKeys") or clean.get("agentKeys") or [])
    clean["executionAgentKeys"] = keys
    clean["agentKeys"] = keys

    agents = list(
        clean.get("recommendedAgents")
        or clean.get("recommending_agents")
        or clean.get("agentNames")
        or []
    )
    clean["recommendedAgents"] = agents
    clean["agentNames"] = agents
    clean["recommendationCount"] = int(
        clean.get("recommendationCount")
        or clean.get("recommendation_count")
        or max(1, len(agents))
    )

    if clean.get("currentReturnRate") is None and clean.get("current_return_pct") is not None:
        clean["currentReturnRate"] = clean["current_return_pct"]
    if clean.get("highestReturnRateSinceBuy") is None and clean.get("max_return_pct") is not None:
        clean["highestReturnRateSinceBuy"] = clean["max_return_pct"]
    if clean.get("lowestReturnRateSinceBuy") is None and clean.get("min_return_pct") is not None:
        clean["lowestReturnRateSinceBuy"] = clean["min_return_pct"]
    if clean.get("reached10PercentAt") is None and clean.get("reached_10_at"):
        clean["reached10PercentAt"] = clean["reached_10_at"]
    if clean.get("daysTo10Percent") is None and clean.get("days_to_10") is not None:
        clean["daysTo10Percent"] = clean["days_to_10"]
    if clean.get("reached20PercentAt") is None and clean.get("reached_20_at"):
        clean["reached20PercentAt"] = clean["reached_20_at"]
    if clean.get("daysTo20Percent") is None and clean.get("days_to_20") is not None:
        clean["daysTo20Percent"] = clean["days_to_20"]

    clean.setdefault("recommendationHistory", clean.get("recommendationHistory") or [])
    return clean


def position_to_ui_snake(row: dict[str, Any]) -> dict[str, Any]:
    """API/문서용 snake_case 보조 필드."""
    buy = int(row.get("buyPrice") or 0)
    cur = int(row.get("currentPrice") or buy)
    return {
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "market": row.get("market"),
        "first_signal_at": row.get("firstSignalAt"),
        "signal_price": row.get("signalPrice"),
        "execution_at": row.get("executionAt"),
        "execution_price": row.get("executionPrice") or buy,
        "execution_market": row.get("executionMarket"),
        "fallback_execution": bool(row.get("fallbackExecution")),
        "entry_type": row.get("entryType"),
        "trigger_type": row.get("triggerType"),
        "has_weekend_risk": bool(row.get("hasWeekendRisk")),
        "trigger_reason": list(row.get("triggerReason") or []),
        "current_price": cur,
        "current_return_pct": float(row.get("currentReturnRate") or 0.0),
        "max_return_pct": float(row.get("highestReturnRateSinceBuy") or 0.0),
        "min_return_pct": float(row.get("lowestReturnRateSinceBuy") or 0.0),
        "reached_10_at": row.get("reached10PercentAt"),
        "days_to_10": row.get("daysTo10Percent"),
        "reached_20_at": row.get("reached20PercentAt"),
        "days_to_20": row.get("daysTo20Percent"),
        "recommending_agents": list(row.get("recommendedAgents") or []),
        "recommendation_count": int(row.get("recommendationCount") or 0),
        "status": row.get("status") or POSITION_STATUS_HOLDING,
    }
