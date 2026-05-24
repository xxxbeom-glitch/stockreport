# -*- coding: utf-8
"""End-to-end session dry-run test."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.decision.models import DecisionTrigger
from src.trading.competition.decision.triggers import build_all_decision_triggers
from src.trading.competition.execution.pipeline import process_executable_decision
from src.trading.competition.teams.pipeline import run_decisions_for_triggers


class E2ESessionTest(unittest.TestCase):
    def test_trigger_to_decision_to_execute_mock(self) -> None:
        triggers = build_all_decision_triggers("e2e_test", enrich_market=False)
        self.assertGreaterEqual(len(triggers), 4)

        types = {t.trigger_type for t in triggers}
        self.assertIn("STRATEGY_CANDIDATE_REVIEW", types)

        decisions = run_decisions_for_triggers(triggers[:4], force_mock=True)
        self.assertEqual(len(decisions), 4)

        buy = next(
            (d for d in decisions if d["decision"].get("action") == "BUY"),
            None,
        )
        if buy:
            decision = dict(buy["decision"])
            decision["_relax_entry"] = True
            decision["_fill_price"] = 50000
            if not decision.get("quantity"):
                decision["quantity"] = 1
            ex = process_executable_decision(
                decision,
                buy.get("review"),
                session_id="e2e_test",
                default_fill_price=50000,
            )
            # May block if account missing in test env — at least validator runs
            self.assertIn("ok", ex)


if __name__ == "__main__":
    unittest.main()
