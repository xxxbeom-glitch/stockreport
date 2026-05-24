# -*- coding: utf-8 -*-
"""REPLAY data validity guards."""

from __future__ import annotations

import unittest

from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS
from src.trading.competition.replay.data_validity import (
    format_data_invalid_reason,
    validate_replay_run_outcome,
    validate_snapshot_for_replay,
)


class ReplayDataValidityTests(unittest.TestCase):
    def test_enrich_failure_reason_includes_provider_attempts(self) -> None:
        enrich = {
            "ok": False,
            "error": "market_data_unavailable",
            "detail": "KIS insufficient",
            "provider_attempts": [
                {"provider": "kis_per_ticker", "ok": False, "error_code": "kis:empty"},
            ],
        }
        snap = {
            "ok": True,
            "eligible_universe": [{"ticker": "005930"}],
            "universe_count": 1,
            "team_scouts": {tid: [] for tid in TEAM_IDS},
            "enrich": enrich,
        }
        v = validate_snapshot_for_replay(snap)
        self.assertFalse(v["valid"])
        self.assertIn("market_data_unavailable", v["reason"])
        self.assertIn("failed_inputs=", v["reason"])
        self.assertIn("kis_per_ticker", v["reason"])

    def test_format_data_invalid_reason(self) -> None:
        reason = format_data_invalid_reason(
            base="market_data_unavailable",
            enrich={
                "detail": "no providers",
                "provider_attempts": [{"call": "get_market_ohlcv", "ok": False, "error_code": "krx_empty_or_non_json_response"}],
            },
        )
        self.assertIn("failed_inputs=", reason)
        self.assertIn("krx_empty_or_non_json_response", reason)

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
