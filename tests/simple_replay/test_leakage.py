"""Leakage guard tests."""

from __future__ import annotations

import unittest

from src.trading.simple_replay.leakage import check_decision_leakage


class LeakageTests(unittest.TestCase):
    def test_future_fact_blocked(self) -> None:
        dec = {
            "supporting_facts": [
                {
                    "source_id": "news:1",
                    "published_at": "2026-01-05T10:00:00+09:00",
                }
            ]
        }
        out = check_decision_leakage(dec, "20260102")
        self.assertFalse(out["ok"])

    def test_same_day_ok(self) -> None:
        dec = {
            "supporting_facts": [
                {
                    "source_id": "scout:A:005930",
                    "published_at": "2026-01-02T14:00:00+09:00",
                }
            ]
        }
        out = check_decision_leakage(dec, "20260102")
        self.assertTrue(out["ok"])


if __name__ == "__main__":
    unittest.main()
