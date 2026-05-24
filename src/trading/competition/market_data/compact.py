"""Compact market data package for AI input (spec §7-1)."""

from __future__ import annotations

from typing import Any, Optional

from src.trading.competition.universe.filters import snapshot_from_kis_quote
from src.trading.competition.universe.models import SymbolSnapshot


def build_compact_symbol_package(
    symbol: SymbolSnapshot,
    *,
    ohlcv_summary: Optional[dict[str, Any]] = None,
    supply_summary: Optional[dict[str, Any]] = None,
    session_tradable: bool = True,
    nxt_eligible: bool = False,
) -> dict[str, Any]:
    """
    Structure key indicators for AI — not raw OHLCV series.

    ohlcv_summary expected keys (when provided):
      change_pct, tv_ratio_20d, breakout_high, below_support,
      avg_trading_value_20d
    supply_summary: institution_net, foreign_net, sector_relative_strength
    """
    ohlcv_summary = ohlcv_summary or {}
    supply_summary = supply_summary or {}

    return {
        "ticker": symbol.ticker_normalized,
        "name": symbol.name,
        "market": symbol.market,
        "current_price_krw": symbol.current_price_krw,
        "change_pct": ohlcv_summary.get("change_pct"),
        "orderable_price_krw": symbol.current_price_krw,
        "tv_ratio_20d": ohlcv_summary.get("tv_ratio_20d"),
        "breakout_high": ohlcv_summary.get("breakout_high"),
        "below_support": ohlcv_summary.get("below_support"),
        "avg_trading_value_20d_krw": symbol.avg_trading_value_20d_krw,
        "institution_flow": supply_summary.get("institution_net"),
        "foreign_flow": supply_summary.get("foreign_net"),
        "sector_relative_strength": supply_summary.get("sector_relative_strength"),
        "session_tradable": session_tradable,
        "nxt_eligible": nxt_eligible,
        "risk_status": symbol.risk_status,
        "risk_notes": symbol.risk_notes,
    }


def build_compact_from_kis(
    ticker: str,
    name: str,
    quote: dict[str, Any] | None,
    *,
    market: str = "UNKNOWN",
    avg_trading_value_20d_krw: Optional[int] = None,
    ohlcv_summary: Optional[dict[str, Any]] = None,
    supply_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Convenience: KIS quote → SymbolSnapshot → compact package."""
    symbol = snapshot_from_kis_quote(
        ticker,
        name,
        quote,
        market=market,
        avg_trading_value_20d_krw=avg_trading_value_20d_krw,
    )
    return build_compact_symbol_package(
        symbol,
        ohlcv_summary=ohlcv_summary,
        supply_summary=supply_summary,
    )
