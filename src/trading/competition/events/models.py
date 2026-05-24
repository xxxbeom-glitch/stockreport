"""Event domain models for competition app."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

from src.trading.competition.models import now_kst_iso

EventType = Literal[
    "DISCLOSURE_POSITIVE",
    "DISCLOSURE_NEGATIVE",
    "DISCLOSURE_RISK",
    "NEWS_MATERIAL",
    "PRICE_VOLUME_ANOMALY",
    "SUPPLY_DEMAND_SHIFT",
    "POSITION_RISK_ALERT",
    "TRADING_STATUS_CHANGE",
]

ScanScope = Literal["eligible_candidate", "position_holding"]
Importance = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Direction = Literal["POSITIVE", "NEGATIVE", "MIXED", "UNKNOWN"]
TeamId = Literal["A", "B", "C", "D"]

EVENT_TYPES: tuple[str, ...] = (
    "DISCLOSURE_POSITIVE",
    "DISCLOSURE_NEGATIVE",
    "DISCLOSURE_RISK",
    "NEWS_MATERIAL",
    "PRICE_VOLUME_ANOMALY",
    "SUPPLY_DEMAND_SHIFT",
    "POSITION_RISK_ALERT",
    "TRADING_STATUS_CHANGE",
)


@dataclass
class EvidenceRef:
    """Original source reference — required for downstream order pipeline."""

    evidence_id: str
    source_type: Literal["dart", "naver_news", "kis", "pykrx", "internal"]
    title: str = ""
    url: str = ""
    published_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RawSignal:
    """Detector output before dedup/analysis."""

    signal_id: str
    ticker: str
    name: str
    event_type: EventType
    scope: ScanScope
    summary: str
    evidence: EvidenceRef
    importance_hint: Importance = "MEDIUM"
    direction_hint: Direction = "UNKNOWN"
    holding_teams: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    detected_at: str = field(default_factory=now_kst_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = self.evidence.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawSignal:
        ev = data.get("evidence") or {}
        return cls(
            signal_id=data["signal_id"],
            ticker=data["ticker"],
            name=data.get("name", data["ticker"]),
            event_type=data["event_type"],
            scope=data["scope"],
            summary=data.get("summary", ""),
            evidence=EvidenceRef(
                evidence_id=ev["evidence_id"],
                source_type=ev.get("source_type", "internal"),
                title=ev.get("title", ""),
                url=ev.get("url", ""),
                published_at=ev.get("published_at", ""),
                raw=ev.get("raw") or {},
            ),
            importance_hint=data.get("importance_hint", "MEDIUM"),
            direction_hint=data.get("direction_hint", "UNKNOWN"),
            holding_teams=list(data.get("holding_teams") or []),
            metrics=dict(data.get("metrics") or {}),
            detected_at=data.get("detected_at", now_kst_iso()),
        )


@dataclass
class AnalyzedEvent:
    """
    Shared event analyzer output (spec §7-3 extended types).
    Analyzer has NO order authority.
    """

    event_id: str
    event_type: EventType
    importance: Importance
    direction: Direction
    summary: str
    direct_tickers: list[str]
    secondary_tickers: list[str] = field(default_factory=list)
    affected_teams: list[str] = field(default_factory=list)
    requires_position_review: bool = False
    evidence_ids: list[str] = field(default_factory=list)
    scope: ScanScope = "eligible_candidate"
    holding_teams: list[str] = field(default_factory=list)
    routing_reason: str = ""
    analyzer_mode: Literal["gemini", "rules"] = "rules"
    created_at: str = field(default_factory=now_kst_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalyzedEvent:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})

    def has_evidence(self) -> bool:
        return bool(self.evidence_ids)


@dataclass
class ActionableEvent:
    """
    Gate-approved event ready for team AI decision calls (Phase 4).
    Extends analyzer output with gate metadata.
    """

    event_id: str
    signal_id: str
    event_type: EventType
    importance: Importance
    direction: Direction
    summary: str
    direct_tickers: list[str]
    affected_teams: list[str]
    evidence_ids: list[str]
    scope: ScanScope
    requires_position_review: bool = False
    holding_teams: list[str] = field(default_factory=list)
    gate_score: int = 0
    gate_auto_pass: bool = False
    market_reaction_confirmed: bool = False
    gate_reasons: list[str] = field(default_factory=list)
    analyzer_mode: Literal["gemini", "rules"] = "rules"
    secondary_tickers: list[str] = field(default_factory=list)
    routing_reason: str = ""
    created_at: str = field(default_factory=now_kst_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_analyzed(
        cls,
        analyzed: AnalyzedEvent,
        *,
        signal_id: str,
        gate_score: int,
        gate_auto_pass: bool,
        market_reaction_confirmed: bool,
        gate_reasons: list[str],
    ) -> ActionableEvent:
        return cls(
            event_id=analyzed.event_id,
            signal_id=signal_id,
            event_type=analyzed.event_type,
            importance=analyzed.importance,
            direction=analyzed.direction,
            summary=analyzed.summary,
            direct_tickers=list(analyzed.direct_tickers),
            secondary_tickers=list(analyzed.secondary_tickers),
            affected_teams=list(analyzed.affected_teams),
            requires_position_review=analyzed.requires_position_review,
            evidence_ids=list(analyzed.evidence_ids),
            scope=analyzed.scope,
            holding_teams=list(analyzed.holding_teams),
            gate_score=gate_score,
            gate_auto_pass=gate_auto_pass,
            market_reaction_confirmed=market_reaction_confirmed,
            gate_reasons=list(gate_reasons),
            analyzer_mode=analyzed.analyzer_mode,
            routing_reason=analyzed.routing_reason,
            created_at=analyzed.created_at,
        )


__all__ = [
    "EvidenceRef",
    "RawSignal",
    "AnalyzedEvent",
    "ActionableEvent",
    "EventType",
    "ScanScope",
    "Importance",
    "Direction",
    "EVENT_TYPES",
]
