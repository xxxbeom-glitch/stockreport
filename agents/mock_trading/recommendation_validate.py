# -*- coding: utf-8 -*-
"""AI 추천 JSON 검증 (후보 티커·가격 관계)."""

from __future__ import annotations

from typing import Any

MISSING_DATA_MEMO = "기관 수급 미수집"


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def validate_recommendation(
    rec: dict[str, Any],
    *,
    allowed_tickers: set[str],
    name_by_ticker: dict[str, str],
) -> tuple[dict[str, Any] | None, str | None]:
    """
    검증 통과 시 정규화된 rec, 실패 시 (None, error_reason).
    """
    if not isinstance(rec, dict):
        return None, "invalid_record"

    ticker = str(rec.get("ticker") or "").zfill(6)
    if not ticker or ticker not in allowed_tickers:
        return None, f"not_in_universe:{ticker}"

    entry = _safe_int(rec.get("entry_price"))
    target = _safe_int(rec.get("target_price"))

    if entry is None or target is None:
        return None, "invalid_price_numbers"

    if not (target > entry):
        return None, f"price_order_invalid:target={target},entry={entry}"

    reasons = [str(x) for x in (rec.get("reasons") or []) if x][:3]
    risks = [str(x) for x in (rec.get("risk_factors") or []) if x][:2]
    if len(reasons) < 2:
        return None, "reasons_count<2"

    evidence = [str(x) for x in (rec.get("evidence_fields") or []) if x]
    evidence = [e for e in evidence if e != "institution_flow"]

    conf = str(rec.get("confidence") or "medium").lower()
    if conf not in ("high", "medium", "low"):
        conf = "medium"

    from agents.mock_trading.plain_language import build_plain_copy

    stock_name = str(rec.get("name") or name_by_ticker.get(ticker, ticker))
    plain = build_plain_copy(
        name=stock_name,
        reason_lines=reasons,
        risk_lines=risks if risks else ["단기 변동성"],
    )
    if rec.get("plain_reason"):
        plain["plainReason"] = str(rec["plain_reason"])
    if rec.get("plain_risk"):
        plain["plainRisk"] = str(rec["plain_risk"])
    if rec.get("view_guide"):
        plain["viewGuide"] = str(rec["view_guide"])

    normalized: dict[str, Any] = {
        "rank": int(rec.get("rank") or 0) or None,
        "ticker": ticker,
        "name": stock_name,
        "sector_group": rec.get("sector_group"),
        "entry_price": entry,
        "entry_range": str(rec.get("entry_range") or f"{entry:,}원 부근"),
        "target_price": target,
        "reasons": reasons,
        "risk_factors": risks if risks else ["단기 변동성"],
        "plain_reason": plain["plainReason"],
        "plain_risk": plain["plainRisk"],
        "view_guide": plain["viewGuide"],
        "confidence": conf,
        "evidence_fields": evidence,
        "missing_data_memo": MISSING_DATA_MEMO,
    }
    if normalized["rank"] is None:
        normalized["rank"] = 0
    return normalized, None


def validate_agent_recommendations(
    raw_list: list[Any],
    *,
    allowed_tickers: set[str],
    name_by_ticker: dict[str, str],
    max_picks: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(valid_recommendations, validation_errors)"""
    valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()

    for i, rec in enumerate(raw_list):
        norm, err = validate_recommendation(
            rec if isinstance(rec, dict) else {},
            allowed_tickers=allowed_tickers,
            name_by_ticker=name_by_ticker,
        )
        if err or norm is None:
            errors.append(
                {
                    "index": i,
                    "ticker": str((rec or {}).get("ticker") if isinstance(rec, dict) else ""),
                    "error": err or "unknown",
                    "raw": rec,
                }
            )
            continue
        if norm["ticker"] in seen:
            errors.append({"index": i, "ticker": norm["ticker"], "error": "duplicate_ticker"})
            continue
        seen.add(norm["ticker"])
        if not norm.get("rank"):
            norm["rank"] = len(valid) + 1
        valid.append(norm)
        if len(valid) >= max_picks:
            break

    return valid, errors
