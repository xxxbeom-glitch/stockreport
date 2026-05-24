"""Phase 4 decision trigger models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from src.trading.competition.models import now_kst_iso

DecisionTriggerType = Literal[
    "STRATEGY_CANDIDATE_REVIEW",
    "ACTIONABLE_EVENT_REVIEW",
    "POSITION_REVIEW",
]

TRIGGER_TYPES: tuple[str, ...] = (
    "STRATEGY_CANDIDATE_REVIEW",
    "ACTIONABLE_EVENT_REVIEW",
    "POSITION_REVIEW",
)

TriggerPriority = Literal["normal", "high", "critical"]


@dataclass
class StrategyCandidate:
    """Compact candidate for team strategy review (spec §6-3)."""

    ticker: str
    name: str
    score: float
    reason_label: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionTrigger:
    """
    Phase 4 AI invocation unit.

    Three trigger types — actionable_events is NOT the sole input:
    - STRATEGY_CANDIDATE_REVIEW: code-scouted team candidates (no event required)
    - ACTIONABLE_EVENT_REVIEW: gate-passed events from actionable_events.jsonl
    - POSITION_REVIEW: held positions on session transition or risk events
    """

    trigger_id: str
    trigger_type: DecisionTriggerType
    team_id: str
    session_id: str
    summary: str
    priority: TriggerPriority = "normal"
    candidates: list[dict[str, Any]] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_kst_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "DecisionTrigger",
    "DecisionTriggerType",
    "StrategyCandidate",
    "TRIGGER_TYPES",
]
