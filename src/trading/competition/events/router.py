"""Route analyzed events to A~D teams."""

from __future__ import annotations

from src.trading.competition.constants import TEAM_IDS
from src.trading.competition.events.models import AnalyzedEvent, RawSignal

# Team affinity by event type (spec §4-2, §6-3)
_TEAM_AFFINITY: dict[str, list[str]] = {
    "DISCLOSURE_POSITIVE": ["B", "A"],
    "DISCLOSURE_NEGATIVE": ["B", "D"],
    "DISCLOSURE_RISK": ["B", "C", "D"],
    "NEWS_MATERIAL": ["B", "A"],
    "PRICE_VOLUME_ANOMALY": ["A", "C"],
    "SUPPLY_DEMAND_SHIFT": ["C", "A"],
    "POSITION_RISK_ALERT": [],  # holding teams only
    "TRADING_STATUS_CHANGE": [],  # holding teams only
}

_POSITION_REVIEW_TYPES = frozenset(
    {
        "POSITION_RISK_ALERT",
        "TRADING_STATUS_CHANGE",
        "DISCLOSURE_RISK",
    }
)


def route_signal(signal: RawSignal) -> AnalyzedEvent:
    """
    Rule-based routing (no LLM). Produces AnalyzedEvent with evidence_ids.
    """
    ev_id = signal.evidence.evidence_id
    if not ev_id:
        raise ValueError("evidence_id required for routing")

    event_id = f"evt_{signal.signal_id}"
    requires_review = (
        signal.scope == "position_holding"
        and signal.event_type in _POSITION_REVIEW_TYPES
    ) or signal.event_type in ("POSITION_RISK_ALERT", "TRADING_STATUS_CHANGE")

    if signal.event_type in ("POSITION_RISK_ALERT", "TRADING_STATUS_CHANGE"):
        affected = list(dict.fromkeys(signal.holding_teams))
        reason = "POSITION_REVIEW_REQUIRED — holding team(s)"
        requires_review = True
    elif signal.scope == "position_holding" and signal.holding_teams:
        base = _TEAM_AFFINITY.get(signal.event_type, ["B"])
        affected = list(dict.fromkeys(signal.holding_teams + base))
        reason = "position context + event affinity"
        if signal.event_type == "DISCLOSURE_RISK":
            requires_review = True
    else:
        affected = list(_TEAM_AFFINITY.get(signal.event_type, ["B"]))
        reason = "event type affinity"

    # Validate team ids
    affected = [t for t in affected if t in TEAM_IDS]

    importance = signal.importance_hint
    if signal.scope == "position_holding" and signal.event_type in (
        "POSITION_RISK_ALERT",
        "TRADING_STATUS_CHANGE",
    ):
        importance = "CRITICAL" if importance != "HIGH" else importance
        if signal.event_type == "TRADING_STATUS_CHANGE":
            importance = "CRITICAL"

    return AnalyzedEvent(
        event_id=event_id,
        event_type=signal.event_type,
        importance=importance,
        direction=signal.direction_hint,
        summary=signal.summary,
        direct_tickers=[signal.ticker],
        secondary_tickers=[],
        affected_teams=affected,
        requires_position_review=requires_review,
        evidence_ids=[ev_id],
        scope=signal.scope,
        holding_teams=list(signal.holding_teams),
        routing_reason=reason,
        analyzer_mode="rules",
    )


__all__ = ["route_signal"]
