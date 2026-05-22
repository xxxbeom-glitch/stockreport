"""20일 거래량·거래대금 비율."""

from __future__ import annotations

import unittest

from agents.market_metrics.ohlcv_ratios import ratios_from_ohlcv_rows


class TestOhlcvRatios(unittest.TestCase):
    def test_trading_value_ratio_20d(self) -> None:
        rows = []
        for i in range(21):
            rows.append(
                {
                    "close": 10000 + i * 10,
                    "volume": 1000 if i < 20 else 2000,
                    "trading_value": 1_000_000_000 if i < 20 else 2_500_000_000,
                }
            )
        r = ratios_from_ohlcv_rows(rows)
        assert r is not None
        self.assertEqual(r["volume_ratio_20d"], 2.0)
        self.assertEqual(r["trading_value_ratio_20d"], 2.5)
        self.assertNotIn("trading_value_vs_3m", r)


if __name__ == "__main__":
    unittest.main()
