"""Calendar tests for SIMPLE_REPLAY."""

from __future__ import annotations

import unittest
from unittest import mock

from src.trading.simple_replay.calendar import normalize_yyyymmdd, resolve_schedule


class CalendarTests(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(normalize_yyyymmdd("2026-01-02"), "20260102")

    def test_resolve_schedule(self) -> None:
        with mock.patch(
            "src.trading.competition.replay.data_provider.next_trading_date_after",
            return_value=("20260105", "kis", []),
        ):
            with mock.patch(
                "src.trading.competition.replay.data_provider.list_trading_dates_result",
                return_value={
                    "ok": True,
                    "dates": ["20260105", "20260106", "20260107", "20260108", "20260109"],
                    "primary_source": "kis",
                },
            ):
                out = resolve_schedule("20260102", 5)
        self.assertEqual(out["buy_date"], "20260105")
        self.assertEqual(len(out["evaluation_dates"]), 5)


if __name__ == "__main__":
    unittest.main()
