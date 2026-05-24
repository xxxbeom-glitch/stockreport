# -*- coding: utf-8
"""Decision schema and mock engine tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.decision.models import DecisionTrigger
from src.trading.competition.teams.mock_provider import mock_main_decision, mock_validator_review
from src.trading.competition.teams.schemas import validate_decision, validate_partner_review


class DecisionSchemaTest(unittest.TestCase):
    def test_hold_decision_valid(self) -> None:
        d = {
            "decision_id": "d1",
            "team_id": "A",
            "session_id": "s1",
            "action": "HOLD",
            "ticker": None,
            "quantity": 0,
            "allocation_krw": 0,
            "order_type": "NONE",
            "reason_label": "wait",
            "evidence_ids": [],
        }
        ok, errs = validate_decision(d)
        self.assertTrue(ok, errs)

    def test_buy_requires_evidence(self) -> None:
        d = {
            "decision_id": "d2",
            "team_id": "A",
            "session_id": "s1",
            "action": "BUY",
            "ticker": "005930",
            "quantity": 1,
            "allocation_krw": 70000,
            "order_type": "MARKET",
            "target_price": 75000,
            "reason_label": "breakout",
            "review_conditions": ["stop"],
            "evidence_ids": [],
        }
        ok, errs = validate_decision(d)
        self.assertFalse(ok)
        self.assertIn("order_requires_evidence_ids", errs)

    def test_mock_strategy_buy(self) -> None:
        inp = {
            "team_id": "A",
            "session_id": "s1",
            "trigger_type": "STRATEGY_CANDIDATE_REVIEW",
            "account": {"cash_krw": 400000, "total_assets_krw": 400000},
            "positions": [],
            "strategy_candidates": [
                {
                    "ticker": "005930",
                    "reason_label": "tv_ratio_2x",
                    "metrics": {"current_price_krw": 70000},
                }
            ],
            "evidence_ids": [],
        }
        d = mock_main_decision(inp, role="A_MAIN")
        ok, _ = validate_decision(d)
        self.assertTrue(ok)
        self.assertEqual(d["action"], "BUY")

    def test_c_validator_approve(self) -> None:
        decision = {
            "decision_id": "d3",
            "team_id": "C",
            "action": "BUY",
            "quantity": 2,
            "allocation_krw": 100000,
            "evidence_ids": ["e1"],
        }
        review = mock_validator_review(decision, role="C_VALIDATOR")
        ok, _ = validate_partner_review(review)
        self.assertTrue(ok)
        self.assertEqual(review["result"], "APPROVE")


class TriggerIsolationTest(unittest.TestCase):
    def test_trigger_carries_team_only(self) -> None:
        t = DecisionTrigger(
            trigger_id="t1",
            trigger_type="STRATEGY_CANDIDATE_REVIEW",
            team_id="D",
            session_id="s1",
            summary="test",
            candidates=[{"ticker": "005930"}],
        )
        self.assertEqual(t.team_id, "D")


if __name__ == "__main__":
    unittest.main()
