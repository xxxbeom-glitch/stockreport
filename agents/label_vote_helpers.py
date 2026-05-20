"""Shared helpers for label voting (KR MVP)."""

from __future__ import annotations

from typing import Any

from data.kr_market import get_kr_fundamentals


def normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    if t.isdigit():
        return t.zfill(6)
    return t.upper()


def enrich_stock_metrics(stock: dict[str, Any], ticker: str) -> dict[str, Any]:
    row = dict(stock)
    market = str(row.get("market", "KR")).upper()
    if market in {"KR", "KOSPI", "KOSDAQ"} and (row.get("per") is None or row.get("pbr") is None):
        fin = get_kr_fundamentals(ticker)
        if row.get("per") is None:
            row["per"] = fin.get("per")
        if row.get("pbr") is None:
            row["pbr"] = fin.get("pbr")
        if row.get("foreign_ownership") is None:
            row["foreign_ownership"] = fin.get("foreign_ownership")
    return row


def grok_supply_verdict(ticker: str, supply: dict[str, Any]) -> dict[str, Any]:
    key = normalize_ticker(ticker)
    verdicts = supply.get("grok_verdicts") or {}
    return verdicts.get(key) or verdicts.get(ticker) or {}


def grok_momentum_verdict(ticker: str, momentum: dict[str, Any]) -> dict[str, Any]:
    key = normalize_ticker(ticker)
    verdicts = momentum.get("grok_verdicts") or {}
    return verdicts.get(key) or verdicts.get(ticker) or {}


def stock_context_payload(stock: dict[str, Any], pipeline: dict[str, Any]) -> dict[str, Any]:
    """Compact JSON-safe context for per-stock vote prompts."""
    ticker = normalize_ticker(str(stock.get("ticker", "")))
    fundamental = (pipeline.get("fundamental") or {}).get("fundamental_scores") or {}
    risk = (pipeline.get("risk") or {}).get("risk_assessments") or {}
    return {
        "ticker": ticker,
        "name": stock.get("name"),
        "theme": stock.get("theme"),
        "price": stock.get("price"),
        "change_rate": stock.get("change_rate"),
        "volume_ratio": stock.get("volume_ratio"),
        "foreign_net": stock.get("foreign_net"),
        "per": stock.get("per"),
        "pbr": stock.get("pbr"),
        "high_52": stock.get("high_52"),
        "low_52": stock.get("low_52"),
        "score": stock.get("score"),
        "market_phase": (pipeline.get("macro") or {}).get("market_phase"),
        "fundamental": fundamental.get(ticker),
        "risk": risk.get(ticker),
        "grok_supply": grok_supply_verdict(ticker, pipeline.get("supply") or {}),
        "grok_momentum": grok_momentum_verdict(ticker, pipeline.get("momentum") or {}),
    }
