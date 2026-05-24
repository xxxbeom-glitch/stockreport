# -*- coding: utf-8 -*-
"""Phase 2 tests — common entry filters."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.universe.filters import assess_kis_risk, passes_common_entry_filter
from src.trading.competition.universe.models import SymbolSnapshot
from src.trading.competition.universe.security_type import classify_security_type


def _sym(**kwargs) -> SymbolSnapshot:
    defaults = {
        "ticker": "005930",
        "name": "삼성전자",
        "market": "KOSPI",
        "security_type": "common",
        "current_price_krw": 70000,
        "avg_trading_value_20d_krw": 5_000_000_000,
        "tradable": True,
    }
    defaults.update(kwargs)
    return SymbolSnapshot(**defaults)


class CommonEntryFilterTest(unittest.TestCase):
    def test_common_stock_passes(self) -> None:
        ok, reason = passes_common_entry_filter(_sym(), team_cash_krw=500_000)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_price_over_100k_excluded_for_new_entry(self) -> None:
        ok, reason = passes_common_entry_filter(
            _sym(current_price_krw=150_000), team_cash_krw=500_000
        )
        self.assertFalse(ok)
        self.assertIn("price_over", reason)

    def test_held_stock_over_100k_not_excluded_on_review(self) -> None:
        ok, _ = passes_common_entry_filter(
            _sym(current_price_krw=150_000),
            is_new_entry=False,
        )
        self.assertTrue(ok)

    def test_low_liquidity_excluded(self) -> None:
        ok, reason = passes_common_entry_filter(
            _sym(avg_trading_value_20d_krw=1_000_000_000), team_cash_krw=500_000
        )
        self.assertFalse(ok)
        self.assertIn("avg_tv_below", reason)

    def test_etf_excluded(self) -> None:
        ok, reason = passes_common_entry_filter(
            _sym(name="KODEX 200 ETF", security_type="etf"), team_cash_krw=500_000
        )
        self.assertFalse(ok)
        self.assertIn("etf", reason)

    def test_preferred_excluded(self) -> None:
        self.assertEqual(classify_security_type("삼성전자우"), "preferred")
        ok, _ = passes_common_entry_filter(
            _sym(name="삼성전자우", security_type="preferred"), team_cash_krw=500_000
        )
        self.assertFalse(ok)

    def test_managed_stock_excluded(self) -> None:
        ok, _ = passes_common_entry_filter(
            _sym(risk_exclude_new_entry=True, risk_status="managed"),
            team_cash_krw=500_000,
        )
        self.assertFalse(ok)

    def test_insufficient_cash(self) -> None:
        ok, reason = passes_common_entry_filter(
            _sym(current_price_krw=80_000), team_cash_krw=50_000
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "insufficient_cash_for_1_share")

    def test_kis_halt_risk(self) -> None:
        risk = assess_kis_risk({"temp_stop_yn": "Y"})
        self.assertTrue(risk["exclude_new_entry"])
        self.assertEqual(risk["risk_status"], "halt")


if __name__ == "__main__":
    unittest.main()
