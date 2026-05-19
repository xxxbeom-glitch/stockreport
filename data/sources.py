"""Source adapters with graceful fallback behavior."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import config
from .models import SourceStatus

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover - import failure path
    yf = None

try:
    from pykrx import stock as pykrx_stock  # type: ignore
except Exception:  # pragma: no cover - import failure path
    pykrx_stock = None


def get_source_statuses() -> list[SourceStatus]:
    """Return status for configured sources."""
    statuses: list[SourceStatus] = []
    for name, meta in config.DATA_SOURCES.items():
        enabled = bool(meta.get("enabled", False))
        required_env = str(meta.get("required_env", "")).strip()
        reason = ""
        if not enabled and required_env:
            reason = f"missing env: {required_env}"
        statuses.append(SourceStatus(name=name, enabled=enabled, reason=reason))
    # Runtime package availability checks
    if yf is None:
        statuses.append(SourceStatus(name="yfinance-runtime", enabled=False, reason="package not installed"))
    if pykrx_stock is None:
        statuses.append(SourceStatus(name="pykrx-runtime", enabled=False, reason="package not installed"))
    return statuses


def fetch_yfinance_history(symbol: str, period: str = "7d") -> Any | None:
    """Fetch yfinance history dataframe; return None on errors."""
    if yf is None:
        return None
    try:
        return yf.Ticker(symbol).history(period=period)
    except Exception:
        return None


def fetch_pykrx_market_ohlcv(date_yyyymmdd: str, market: str) -> Any | None:
    """Fetch pykrx OHLCV dataframe; return None on errors."""
    if pykrx_stock is None:
        return None
    try:
        return pykrx_stock.get_market_ohlcv(date_yyyymmdd, market=market)
    except Exception:
        return None


def fetch_pykrx_trading_value(date_yyyymmdd: str, market: str = "KOSPI") -> Any | None:
    """Fetch pykrx trading value dataframe; return None on errors."""
    if pykrx_stock is None:
        return None
    try:
        if hasattr(pykrx_stock, "get_market_trading_value_by_ticker"):
            return pykrx_stock.get_market_trading_value_by_ticker(date_yyyymmdd, market=market)
        from .kr_market import _fetch_foreign_net_purchases_frame

        frame = _fetch_foreign_net_purchases_frame(market, date_yyyymmdd)
        if frame is None:
            return None
        if "순매수거래대금" in frame.columns:
            frame = frame.rename(columns={"순매수거래대금": "외국인"})
        elif "순매수거래량" in frame.columns:
            frame = frame.rename(columns={"순매수거래량": "외국인"})
        return frame
    except Exception:
        return None


def fetch_ticker_name(ticker: str) -> str:
    """Resolve ticker name if pykrx is available."""
    if pykrx_stock is None:
        return ticker
    try:
        return str(pykrx_stock.get_market_ticker_name(ticker))
    except Exception:
        return ticker


def optional_grok_prompt(prompt: str) -> str:
    """Placeholder for Grok integration with no-key fallback."""
    if not config.GROK_API_KEY:
        return ""
    # Keep local-only compatibility. Real network client can be added later.
    _ = prompt
    return ""


def optional_gemini_prompt(prompt: str) -> str:
    """Placeholder for Gemini integration with no-key fallback."""
    if not config.GEMINI_API_KEY:
        return ""
    _ = prompt
    return ""


def optional_slack_notify(text: str) -> bool:
    """Placeholder for Slack notification with no-key fallback."""
    if not config.SLACK_BOT_TOKEN:
        return False
    _ = text
    return False


def optional_firebase_store(payload: dict[str, Any]) -> bool:
    """Placeholder for Firebase persistence with no-key fallback."""
    if not config.FIREBASE_STORAGE_BUCKET:
        return False
    _ = payload
    return False


def source_status_dicts() -> list[dict[str, Any]]:
    """Get source statuses in dict format for JSON-friendly outputs."""
    return [asdict(item) for item in get_source_statuses()]
