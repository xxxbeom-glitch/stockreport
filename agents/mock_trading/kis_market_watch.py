# -*- coding: utf-8 -*-
"""KIS 시세·거래량/거래대금·NXT 애프터마켓 가능 여부 (감시·실행용)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 환경변수: always | never | heuristic (기본)
NXT_MODE = os.getenv("MOCK_TRADING_NXT_MODE", "heuristic").strip().lower()
NXT_TICKERS_ENV = os.getenv("MOCK_TRADING_NXT_TICKERS", "")


def _nxt_allowlist() -> set[str]:
    if not NXT_TICKERS_ENV.strip():
        return set()
    return {t.strip().zfill(6) for t in NXT_TICKERS_ENV.split(",") if t.strip()}


def fetch_quote(ticker: str) -> dict[str, Any] | None:
    """KIS inquire-price 스냅샷."""
    try:
        from data.kis_client import get_price

        return get_price(str(ticker).zfill(6))
    except Exception as exc:
        logger.warning("[%s] KIS quote failed: %s", ticker, exc)
        return None


def quote_to_int_price(quote: dict[str, Any] | None) -> int:
    if not quote:
        return 0
    try:
        return int(round(float(quote.get("price") or 0)))
    except (TypeError, ValueError):
        return 0


def is_nxt_aftermarket_tradeable(ticker: str, quote: dict[str, Any] | None = None) -> bool:
    """
    NXT 애프터마켓 거래 가능 여부.
    - MOCK_TRADING_NXT_MODE=always|never
    - MOCK_TRADING_NXT_TICKERS=005930,000660
    - heuristic: KIS raw 필드 또는 대형주 추정
    """
    code = str(ticker).zfill(6)
    if NXT_MODE == "always":
        return True
    if NXT_MODE == "never":
        return False
    if code in _nxt_allowlist():
        return True

    quote = quote or fetch_quote(code)
    if not quote:
        return False
    raw = quote.get("raw") or {}
    if not isinstance(raw, dict):
        return False
    for key in (
        "nxt_trad_psbl_yn",
        "NXT_TRAD_PSBL_YN",
        "nxt_trad_yn",
        "NXT_TRAD_YN",
    ):
        val = str(raw.get(key) or "").strip().upper()
        if val in ("Y", "YES", "1", "TRUE"):
            return True
        if val in ("N", "NO", "0", "FALSE"):
            return False
    return False


def fetch_execution_price(
    ticker: str,
    *,
    execution_market: str,
    fallback_execution: bool,
) -> dict[str, Any]:
    """
    실행 시점 가격 조회.
    NXT_AFTER_MARKET: 애프터마켓 시세(동일 API + NXT 플래그) 또는 정규 현재가.
    KRX_REGULAR: 정규장 현재가(09:10 배치 가정).
    """
    quote = fetch_quote(ticker)
    price = quote_to_int_price(quote)
    source = "kis_inquire_price"
    if execution_market == "NXT_AFTER_MARKET" and not fallback_execution:
        source = "kis_nxt_aftermarket_or_regular"
    return {
        "ticker": str(ticker).zfill(6),
        "price": price,
        "quote": quote,
        "source": source,
        "execution_market": execution_market,
        "fallback_execution": fallback_execution,
    }


def volume_spike_signal(
    ticker: str,
    *,
    min_change_rate: float = 3.0,
    quote: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """거래량·등락 기반 급등 후보 신호 (자동매수 아님)."""
    quote = quote or fetch_quote(ticker)
    if not quote:
        return None
    change = float(quote.get("change_rate") or 0.0)
    volume = float(quote.get("volume") or 0.0)
    if change < min_change_rate and volume <= 0:
        return None
    reasons: list[str] = []
    if change >= min_change_rate:
        reasons.append(f"등락률 {change:+.2f}%")
    if volume > 0:
        reasons.append("거래량 데이터 갱신")
    if not reasons:
        return None
    return {
        "ticker": str(ticker).zfill(6),
        "signal_type": "volume_price",
        "change_rate": change,
        "volume": volume,
        "reasons": reasons,
    }


def refresh_tickers_prices(tickers: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw in tickers:
        t = str(raw).zfill(6)
        if not t:
            continue
        p = quote_to_int_price(fetch_quote(t))
        if p > 0:
            out[t] = p
    return out
