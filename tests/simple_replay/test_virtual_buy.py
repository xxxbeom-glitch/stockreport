"""Virtual buy tests."""

from __future__ import annotations

import unittest
from unittest import mock

from src.trading.simple_replay.virtual_buy import virtual_buy


class VirtualBuyTests(unittest.TestCase):
    def test_skip_returns_none(self) -> None:
        self.assertIsNone(virtual_buy({"action": "SKIP"}, buy_date="20260105", name_by_ticker={}))

    def test_buy_computes_quantity(self) -> None:
        dec = {
            "action": "BUY",
            "team_id": "A",
            "selected_stock": {"stock_code": "005930", "stock_name": "삼성전자"},
            "reason_label": "test",
        }
        with mock.patch(
            "src.trading.simple_replay.virtual_buy.fill_price_krw",
            return_value=(70000, "kis_open", None),
        ):
            pos = virtual_buy(dec, buy_date="20260105", name_by_ticker={"005930": "삼성전자"})
        self.assertIsNotNone(pos)
        assert pos is not None
        self.assertGreaterEqual(pos["quantity"], 1)
        self.assertLessEqual(pos["invested_amount"], 500_000)
        self.assertEqual(pos["invested_amount"], pos["quantity"] * 70000)


if __name__ == "__main__":
    unittest.main()
