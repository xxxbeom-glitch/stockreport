# -*- coding: utf-8 -*-
"""REPLAY universe enrich — KIS-first without KRX credentials."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.trading.competition.ops.historical_seed import enrich_universe_historical


class ReplayHistoricalEnrichTests(unittest.TestCase):
    def test_kis_first_skips_pykrx_without_krx_creds(self) -> None:
        stocks = [{"ticker": "005930"}, {"ticker": "000660"}] * 6
        kis_result = {
            "ok": True,
            "enriched": 12,
            "failures": [],
            "errors": [],
            "source": "kis_per_ticker",
        }
        with patch(
            "src.trading.competition.replay.pykrx_safe.krx_credentials_configured",
            return_value=False,
        ):
            with patch(
                "src.trading.competition.replay.data_provider._kis_ready",
                return_value=True,
            ):
                with patch(
                    "src.trading.competition.ops.historical_seed._replay_prev_trading_date",
                    return_value="20251230",
                ):
                    with patch(
                        "src.trading.competition.replay.data_provider.enrich_universe_rows_kis",
                        return_value=kis_result,
                    ) as mock_kis:
                        out = enrich_universe_historical(stocks, "20260102")
        mock_kis.assert_called_once()
        self.assertTrue(out["ok"])
        self.assertEqual(out.get("primary_source"), "kis_per_ticker")

    def test_no_krx_no_kis_returns_market_data_unavailable(self) -> None:
        stocks = [{"ticker": "005930"}]
        with patch(
            "src.trading.competition.replay.data_provider._kis_ready",
            return_value=False,
        ):
            with patch(
                "src.trading.competition.replay.pykrx_safe.krx_credentials_configured",
                return_value=False,
            ):
                out = enrich_universe_historical(stocks, "20260102")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "market_data_unavailable")
        self.assertTrue(out.get("krx_login_required"))


if __name__ == "__main__":
    unittest.main()
