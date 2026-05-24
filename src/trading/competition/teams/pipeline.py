"""Team decision pipeline."""

from __future__ import annotations

from typing import Any

from src.trading.competition.decision.models import DecisionTrigger
from src.trading.competition.teams.engine import process_trigger


def run_decisions_for_triggers(
    triggers: list[DecisionTrigger],
    *,
    force_mock: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for trig in triggers:
        results.append(process_trigger(trig, force_mock=force_mock))
    return results
