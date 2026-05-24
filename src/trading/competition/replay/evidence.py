"""Point-in-time evidence records for replay snapshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TimestampConfidence = Literal["verified", "inferred", "unavailable"]
SourceType = Literal[
    "price",
    "volume",
    "investor_flow",
    "dart",
    "news",
    "sector",
    "session",
    "scout",
]


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_type: SourceType
    observed_at: str
    published_at: str
    available_at: str
    fetched_at: str
    decision_at: str
    included: bool = True
    exclusion_reason: str | None = None
    timestamp_confidence: TimestampConfidence = "verified"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence_usable_for_decision(rec: EvidenceRecord) -> bool:
    if not rec.included:
        return False
    if rec.timestamp_confidence != "verified":
        return False
    return rec.available_at <= rec.decision_at


def make_price_evidence(
    *,
    evidence_id: str,
    ticker: str,
    decision_at: str,
    trading_date: str,
    close_krw: int,
    change_rate_pct: float | None = None,
) -> EvidenceRecord:
    ts = f"{trading_date[:4]}-{trading_date[4:6]}-{trading_date[6:8]}T15:30:00+09:00"
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_type="price",
        observed_at=ts,
        published_at=ts,
        available_at=ts,
        fetched_at=decision_at,
        decision_at=decision_at,
        included=True,
        timestamp_confidence="verified",
        payload={
            "ticker": ticker,
            "close_krw": close_krw,
            "change_rate_pct": change_rate_pct,
            "trading_date": trading_date,
        },
    )


def make_flow_evidence(
    *,
    evidence_id: str,
    ticker: str,
    decision_at: str,
    trading_date: str,
    foreign_net: float | None,
) -> EvidenceRecord:
    """Investor flow — verified only when pykrx date matches decision day close."""
    ts = f"{trading_date[:4]}-{trading_date[4:6]}-{trading_date[6:8]}T15:30:00+09:00"
    if foreign_net is None:
        return EvidenceRecord(
            evidence_id=evidence_id,
            source_type="investor_flow",
            observed_at=ts,
            published_at=ts,
            available_at=ts,
            fetched_at=decision_at,
            decision_at=decision_at,
            included=False,
            exclusion_reason="foreign_net_unavailable",
            timestamp_confidence="unavailable",
            payload={"ticker": ticker},
        )
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_type="investor_flow",
        observed_at=ts,
        published_at=ts,
        available_at=ts,
        fetched_at=decision_at,
        decision_at=decision_at,
        included=True,
        timestamp_confidence="verified",
        payload={"ticker": ticker, "foreign_net": foreign_net},
    )


def make_news_unverified_placeholder(
    *,
    evidence_id: str,
    decision_at: str,
    reason: str,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_type="news",
        observed_at="",
        published_at="",
        available_at="",
        fetched_at=decision_at,
        decision_at=decision_at,
        included=False,
        exclusion_reason=reason,
        timestamp_confidence="unavailable",
        payload={"note": "news_not_replayed_for_point_in_time"},
    )
