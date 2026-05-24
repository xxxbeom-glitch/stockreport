"""Decision trigger pipeline."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.trading.competition.decision.store import save_trigger_batch
from src.trading.competition.decision.triggers import build_all_decision_triggers
from src.trading.competition.models import now_kst_iso


def run_trigger_build(
    session_id: str,
    *,
    include_strategy: bool = True,
    include_actionable: bool = True,
    include_position: bool = True,
    session_transition: bool = True,
    enrich_market: bool = True,
) -> dict[str, Any]:
    """Build and persist Phase 4 decision triggers for a session."""
    triggers = build_all_decision_triggers(
        session_id,
        include_strategy=include_strategy,
        include_actionable=include_actionable,
        include_position=include_position,
        session_transition=session_transition,
        enrich_market=enrich_market,
    )

    by_type = Counter(t.trigger_type for t in triggers)
    by_team = Counter(t.team_id for t in triggers)

    summary = {
        "generated_at": now_kst_iso(),
        "session_id": session_id,
        "trigger_total": len(triggers),
        "by_trigger_type": dict(by_type),
        "by_team": dict(by_team),
        "inputs": {
            "strategy_from": "eligible_entry_universe.json",
            "actionable_from": "actionable_events.jsonl",
            "position_from": "positions.json",
        },
    }

    payload = [t.to_dict() for t in triggers]
    save_trigger_batch(payload, summary)

    return {
        "ok": True,
        "summary": summary,
        "triggers": payload,
    }
