"""Multi-horizon evaluation storage."""

from __future__ import annotations

import unittest
from unittest import mock

from src.trading.simple_replay.evaluation import evaluate_position_horizons


class MultiHorizonTests(unittest.TestCase):
    def test_partial_20d(self) -> None:
        pos = {
            "team_id": "A",
            "ticker": "005930",
            "buy_price": 70000,
            "quantity": 7,
            "remaining_cash": 10000,
        }
        horizons = {
            "5": {"horizon_days": 5, "dates": ["20260105", "20260106", "20260107", "20260108", "20260109"]},
            "10": {"horizon_days": 10, "dates": ["20260105", "20260106"]},
            "20": {"horizon_days": 20, "dates": []},
        }
        closes = {
            "20260105": 71000,
            "20260106": 72000,
            "20260107": 70000,
            "20260108": 73000,
            "20260109": 75000,
        }

        with mock.patch(
            "src.trading.simple_replay.evaluation.close_price_krw",
            side_effect=lambda t, d: (closes.get(d), None),
        ):
            out = evaluate_position_horizons(pos, horizons)
        self.assertEqual(len(out["daily_evaluations"]), 5)
        ev10 = out["evaluations"]["10"]
        self.assertEqual(ev10["status"], "evaluation_pending")
        ev20 = out["evaluations"]["20"]
        self.assertEqual(ev20["status"], "insufficient_future_data")


if __name__ == "__main__":
    unittest.main()
