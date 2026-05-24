# -*- coding: utf-8
"""Team D scout filter tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.decision.d_scout import evaluate_d_candidate
from src.trading.competition.decision.strategy_scouts import scout_team_d


def _row(**kwargs) -> dict:
    base = {
        "ticker": "000660",
        "name": "SK하이닉스",
        "avg_trading_value_20d_krw": 6_000_000_000,
        "change_rate_pct": -5.0,
        "prior_change_pct": -8.0,
    }
    base.update(kwargs)
    return base


class DScoutFilterTest(unittest.TestCase):
    def test_deep_drop_without_rebound_excluded(self) -> None:
        row = _row(
            change_rate_pct=-10.0,
            prior_change_pct=-11.0,
            current_trading_value_krw=3_000_000_000,
            avg_trading_value_20d_krw=6_000_000_000,
        )
        ok, reason, _ = evaluate_d_candidate(row)
        self.assertFalse(ok)
        self.assertEqual(reason, "drop_without_rebound_signal")

    def test_risk_disclosure_ticker_excluded(self) -> None:
        row = _row(
            rebound_from_low_pct=2.5,
            tv_ratio_20d=1.2,
            risk_status="normal",
        )
        ok, reason, _ = evaluate_d_candidate(row, blocked_tickers={"000660"})
        self.assertFalse(ok)
        self.assertEqual(reason, "blocked_ticker_risk_or_bad_news")

    def test_stabilization_rebound_allowed(self) -> None:
        row = _row(rebound_from_low_pct=2.0, tv_ratio_20d=1.1)
        ok, reason, signals = evaluate_d_candidate(row)
        self.assertTrue(ok)
        self.assertEqual(reason, "")
        self.assertTrue(signals)

    def test_managed_stock_excluded(self) -> None:
        row = _row(rebound_from_low_pct=3.0, risk_status="managed")
        ok, reason, _ = evaluate_d_candidate(row)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("risk_status_"))

    def test_scout_team_d_filters_batch(self) -> None:
        stocks = [
            _row(ticker="111111", change_rate_pct=-6.0, rebound_from_low_pct=2.0),
            _row(ticker="222222", change_rate_pct=-9.0, prior_change_pct=-9.5),
        ]
        events = [
            {
                "event_type": "DISCLOSURE_NEGATIVE",
                "importance": "HIGH",
                "direction": "NEGATIVE",
                "direct_tickers": ["222222"],
            }
        ]
        cands = scout_team_d(stocks, actionable_events=events)
        tickers = {c.ticker for c in cands}
        self.assertIn("111111", tickers)
        self.assertNotIn("222222", tickers)


if __name__ == "__main__":
    unittest.main()
