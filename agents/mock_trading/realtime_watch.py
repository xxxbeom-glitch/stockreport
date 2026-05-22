# -*- coding: utf-8 -*-
"""
실시간 감시 — KIS 시세·거래량, DART 공시.
신호만 기록하고 자동 가상매수하지 않음.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.mock_trading.dart_position_watch import fetch_disclosure_alerts
from agents.mock_trading.intraday_alert_store import append_candidate, list_candidates
from agents.mock_trading.kis_market_watch import (
    fetch_quote,
    quote_to_int_price,
    refresh_tickers_prices,
    volume_spike_signal,
)
from agents.mock_trading.virtual_positions_store import list_positions

logger = logging.getLogger(__name__)


def _watch_tickers() -> list[str]:
    tickers: set[str] = set()
    for pos in list_positions():
        t = str(pos.get("ticker") or "").zfill(6)
        if t:
            tickers.add(t)
    return sorted(tickers)


def scan_intraday_signals(
    tickers: list[str] | None = None,
    *,
    min_change_rate: float = 3.0,
) -> list[dict[str, Any]]:
    """거래대금·거래량·급등 후보 (자동매수 없음)."""
    codes = tickers or _watch_tickers()
    signals: list[dict[str, Any]] = []
    open_tickers = {
        str(c.get("ticker") or "").zfill(6) for c in list_candidates(status="OPEN")
    }

    for ticker in codes:
        quote = fetch_quote(ticker)
        sig = volume_spike_signal(ticker, min_change_rate=min_change_rate, quote=quote)
        if not sig:
            continue
        if ticker in open_tickers:
            continue
        sig["name"] = ""
        for pos in list_positions():
            if str(pos.get("ticker")).zfill(6) == ticker:
                sig["name"] = pos.get("name") or ""
                break
        signals.append(sig)
    return signals


def scan_dart_signals(tickers: list[str] | None = None) -> list[dict[str, Any]]:
    codes = tickers or _watch_tickers()
    out: list[dict[str, Any]] = []
    open_tickers = {
        str(c.get("ticker") or "").zfill(6) for c in list_candidates(status="OPEN")
    }
    for ticker in codes:
        for alert in fetch_disclosure_alerts(ticker):
            if ticker in open_tickers:
                continue
            out.append(alert)
    return out


def run_watch_cycle(
    *,
    min_change_rate: float = 3.0,
    include_dart: bool = True,
    persist_candidates: bool = True,
) -> dict[str, Any]:
    tickers = _watch_tickers()
    prices = refresh_tickers_prices(tickers)

    from agents.mock_trading.virtual_positions_store import refresh_position_prices

    if prices:
        refresh_position_prices(prices)

    volume_signals = scan_intraday_signals(tickers, min_change_rate=min_change_rate)
    dart_signals = scan_dart_signals(tickers) if include_dart else []
    created: list[dict[str, Any]] = []

    for sig in volume_signals + dart_signals:
        row = {
            "ticker": sig.get("ticker"),
            "name": sig.get("name") or "",
            "signal_type": sig.get("signal_type"),
            "reasons": list(sig.get("reasons") or []),
            "trigger_reason": list(sig.get("reasons") or []),
            "snapshot_price": quote_to_int_price(fetch_quote(str(sig.get("ticker")))),
            "raw": {k: v for k, v in sig.items() if k not in ("raw",)},
        }
        if persist_candidates:
            created.append(append_candidate(row))
        else:
            created.append(row)

    return {
        "ok": True,
        "watched_tickers": len(tickers),
        "prices_refreshed": len(prices),
        "volume_signals": len(volume_signals),
        "dart_signals": len(dart_signals),
        "candidates_created": len(created),
        "candidates": created,
    }
