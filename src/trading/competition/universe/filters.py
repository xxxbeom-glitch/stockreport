"""Common new-entry filters for KOSPI/KOSDAQ universe (spec §2-2)."""

from __future__ import annotations

from typing import Any, Optional

from src.trading.competition.constants import (
    MAX_ENTRY_PRICE_KRW,
    MIN_AVG_TRADING_VALUE_KRW,
)
from src.trading.competition.universe.models import SymbolSnapshot
from src.trading.competition.universe.security_type import classify_security_type


def assess_kis_risk(raw: dict[str, Any] | None) -> dict[str, Any]:
    """
    KIS inquire-price raw → risk flags.
    Mirrors agents/mock_trading/universe_builder._kis_risk_assessment pattern.
    """
    out: dict[str, Any] = {
        "risk_status": "normal",
        "exclude_new_entry": False,
        "tradable": None,
        "notes": [],
    }
    if not raw or not isinstance(raw, dict):
        return out

    halt = str(raw.get("temp_stop_yn") or raw.get("stck_stop_yn") or "").upper()
    if halt in ("Y", "1"):
        out.update(
            risk_status="halt",
            exclude_new_entry=True,
            tradable=False,
            notes=["거래정지"],
        )
        return out

    managed = str(raw.get("mang_issu_cls_code") or "").upper()
    if managed in ("Y", "1"):
        out.update(
            risk_status="managed",
            exclude_new_entry=True,
            notes=["관리종목"],
        )
        return out

    warn_cls = str(raw.get("mrkt_warn_cls_code") or "").strip().zfill(2)
    if warn_cls == "03":
        out.update(risk_status="risk", exclude_new_entry=True, notes=["투자위험"])
        return out
    if warn_cls == "02":
        out.update(risk_status="warning", exclude_new_entry=True, notes=["투자경고"])
        return out

    # 정리매매 — KIS field varies; check common liquidation flags
    liq = str(raw.get("sltr_yn") or raw.get("lstn_abol_yn") or "").upper()
    if liq in ("Y", "1"):
        out.update(
            risk_status="liquidation",
            exclude_new_entry=True,
            notes=["정리매매/상장폐지위험"],
        )
        return out

    out["tradable"] = True
    return out


def passes_common_entry_filter(
    symbol: SymbolSnapshot,
    *,
    team_cash_krw: Optional[int] = None,
    is_new_entry: bool = True,
) -> tuple[bool, str]:
    """
    Apply spec §2-2 common filters for new entry.

    When is_new_entry=False (existing position review), price cap and
    some product-type rules do not exclude re-evaluation.
    """
    if symbol.security_type != "common":
        if is_new_entry:
            return False, f"excluded_security_type:{symbol.security_type}"

    if is_new_entry and symbol.risk_exclude_new_entry:
        return False, f"risk:{symbol.risk_status}"

    if is_new_entry:
        price = symbol.current_price_krw
        if price is None:
            return False, "no_price"
        if price > MAX_ENTRY_PRICE_KRW:
            return False, f"price_over_{MAX_ENTRY_PRICE_KRW}"

        avg_tv = symbol.avg_trading_value_20d_krw
        if avg_tv is None:
            return False, "no_avg_trading_value_20d"
        if avg_tv < MIN_AVG_TRADING_VALUE_KRW:
            return False, f"avg_tv_below_{MIN_AVG_TRADING_VALUE_KRW}"

        if team_cash_krw is not None and price > 0:
            if team_cash_krw < price:
                return False, "insufficient_cash_for_1_share"

    if symbol.tradable is False:
        return False, "not_tradable"

    return True, "ok"


def snapshot_from_kis_quote(
    ticker: str,
    name: str,
    quote: dict[str, Any] | None,
    *,
    market: str = "UNKNOWN",
    avg_trading_value_20d_krw: Optional[int] = None,
) -> SymbolSnapshot:
    """Build SymbolSnapshot from KIS quote dict."""
    raw = (quote or {}).get("raw") or {}
    price = quote.get("current_price") if quote else None
    if price is None and raw:
        try:
            price = int(float(raw.get("stck_prpr") or 0))
        except (TypeError, ValueError):
            price = None

    risk = assess_kis_risk(raw if isinstance(raw, dict) else None)
    sec_type = classify_security_type(name, ticker)

    return SymbolSnapshot(
        ticker=str(ticker).zfill(6),
        name=name,
        market=market if market in ("KOSPI", "KOSDAQ") else "UNKNOWN",  # type: ignore[arg-type]
        security_type=sec_type,  # type: ignore[arg-type]
        current_price_krw=int(price) if price else None,
        avg_trading_value_20d_krw=avg_trading_value_20d_krw,
        risk_status=risk["risk_status"],
        risk_exclude_new_entry=bool(risk["exclude_new_entry"]),
        risk_notes=list(risk.get("notes") or []),
        tradable=risk.get("tradable") if risk.get("tradable") is not None else True,
        raw=raw if isinstance(raw, dict) else {},
    )
