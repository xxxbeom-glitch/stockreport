"""Five-day evaluation tests."""

from __future__ import annotations

import unittest
from unittest import mock

from src.trading.simple_replay.evaluation import evaluate_position, team_totals


class EvaluationTests(unittest.TestCase):
    def test_evaluate_five_days(self) -> None:
        pos = {
            "team_id": "A",
            "ticker": "005930",
            "buy_price": 70000,
            "quantity": 7,
            "remaining_cash": 10000,
            "target_price": 80000,
        }
        dates = ["20260105", "20260106", "20260107", "20260108", "20260109"]
        closes = [71000, 72000, 70000, 73000, 75000]

        with mock.patch(
            "src.trading.simple_replay.evaluation.close_price_krw",
            side_effect=lambda t, d: (closes[dates.index(d)], None),
        ):
            out = evaluate_position(pos, dates)
        self.assertEqual(len(out["daily_evaluations"]), 5)
        self.assertEqual(out["final_return_pct"], round((75000 - 70000) / 70000 * 100, 2))

    def test_team_totals_skip(self) -> None:
        t = team_totals("C", position=None, skip=True)
        self.assertEqual(t["total_asset"], 500_000)


if __name__ == "__main__":
    unittest.main()
