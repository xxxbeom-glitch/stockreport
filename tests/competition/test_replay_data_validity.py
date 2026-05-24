# -*- coding: utf-8 -*-
"""REPLAY data validity guards."""

from __future__ import annotations

import unittest

from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS
from src.trading.competition.replay.data_validity import (
    validate_replay_run_outcome,
    validate_snapshot_for_replay,
)


class ReplayDataValidityTests(unittest.TestCase):
    def test_rejects_empty_universe(self) -> None:
        snap = {"ok": True, "eligible_universe": [], "universe_count": 0, "team_scouts": {}}
        v = validate_snapshot_for_replay(snap)
        self.assertFalse(v["valid"])
        self.assertEqual(v["data_status"], "data_invalid")

    def test_rejects_no_scout_candidates(self) -> None:
        snap = {
            "ok": True,
            "eligible_universe": [{"ticker": "005930", "current_price_krw": 70000}],
            "universe_count": 1,
            "team_scouts": {tid: [] for tid in TEAM_IDS},
            "enrich": {"ok": True},
        }
        v = validate_snapshot_for_replay(snap)
        self.assertFalse(v["valid"])
        self.assertEqual(v["reason"], "no_scout_candidates_for_any_team")

    def test_all_hold_with_scouts_is_valid(self) -> None:
        snap = {
            "ok": True,
            "eligible_universe": [{"ticker": "005930", "current_price_krw": 70000}],
            "universe_count": 1,
            "team_scouts": {"A": [{"ticker": "005930"}], "B": [], "C": [], "D": []},
            "enrich": {"ok": True},
        }
        accounts = {
            tid: {"cash_krw": INITIAL_CASH_KRW, "total_assets_krw": INITIAL_CASH_KRW, "positions": []}
            for tid in TEAM_IDS
        }
        team_results = {tid: {"action": "HOLD", "status": "no_order"} for tid in TEAM_IDS}
        v = validate_replay_run_outcome(snap, accounts=accounts, team_results=team_results)
        self.assertTrue(v["valid"])
        self.assertEqual(v["data_status"], "all_hold")
        self.assertTrue(v.get("all_hold"))


if __name__ == "__main__":
    unittest.main()
