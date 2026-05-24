"""Source validation for raw signals."""

from __future__ import annotations

from src.trading.competition.events.models import RawSignal

VALID_SOURCE_TYPES = frozenset({"dart", "naver_news", "kis", "pykrx", "internal"})


def validate_signal(signal: RawSignal) -> tuple[bool, str]:
    """
    Validate evidence and source before scoring.

    Returns (ok, reason_code).
    """
    ev = signal.evidence
    if not ev.evidence_id or not str(ev.evidence_id).strip():
        return False, "missing_evidence_id"

    if ev.source_type not in VALID_SOURCE_TYPES:
        return False, f"invalid_source_type:{ev.source_type}"

    if ev.source_type == "dart" and not ev.evidence_id.startswith("dart:"):
        return False, "invalid_dart_evidence_format"

    if ev.source_type == "naver_news" and not ev.evidence_id.startswith("news:"):
        return False, "invalid_news_evidence_format"

    if not signal.ticker or len(str(signal.ticker).zfill(6)) != 6:
        return False, "invalid_ticker"

    if signal.event_type not in (
        "DISCLOSURE_POSITIVE",
        "DISCLOSURE_NEGATIVE",
        "DISCLOSURE_RISK",
        "NEWS_MATERIAL",
        "PRICE_VOLUME_ANOMALY",
        "SUPPLY_DEMAND_SHIFT",
        "POSITION_RISK_ALERT",
        "TRADING_STATUS_CHANGE",
    ):
        return False, f"invalid_event_type:{signal.event_type}"

    return True, "ok"
