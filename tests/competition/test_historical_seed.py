# -*- coding: utf-8 -*-
"""Tests for historical seed helpers (no network / no LLM)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.ops.historical_seed import (
    DEFAULT_AS_OF,
    build_seed_slack_summary,
    historical_close_quote,
    seed_execution_meta,
    seed_session_id,
)


class HistoricalSeedTest(unittest.TestCase):
    def test_seed_session_id(self) -> None:
        self.assertEqual(seed_session_id("20260522"), "seed_20260522_close")

    def test_seed_execution_meta(self) -> None:
        meta = seed_execution_meta("20260522")
        self.assertEqual(meta["execution_mode"], "historical_seed")
        self.assertEqual(meta["as_of_date"], "2026-05-22")
        self.assertTrue(meta["reset_required_before_live"])

    def test_historical_close_quote_from_universe(self) -> None:
        universe = {"005930": {"ticker": "005930", "name": "삼성전자", "current_price_krw": 56000}}
        quote = historical_close_quote("005930", universe, DEFAULT_AS_OF)
        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual(quote["price"], 56000)
        self.assertEqual(quote["source"], "pykrx_close")

    def test_slack_summary_contains_required_lines(self) -> None:
        report = {
            "as_of_display": "2026-05-22",
            "run_purpose": "ui_storage_flow_verification",
            "session_id": "seed_20260522_close",
            "teams": {
                "A": {"fills": [], "cash_krw": 500000, "total_assets_krw": 500000, "action": "HOLD"},
                "B": {"fills": [], "cash_krw": 500000, "total_assets_krw": 500000, "action": "WAIT"},
                "C": {"fills": [], "cash_krw": 500000, "total_assets_krw": 500000, "action": "HOLD"},
                "D": {"fills": [], "cash_krw": 500000, "total_assets_krw": 500000, "action": "HOLD"},
            },
        }
        text = build_seed_slack_summary(report)
        self.assertIn("[AI 투자 경쟁앱] 실제 데이터 초기 모의운용 테스트 완료", text)
        self.assertIn("2026-05-22", text)
        self.assertIn("초기화", text)


if __name__ == "__main__":
    unittest.main()
