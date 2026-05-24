"""REPLAY data provider — KIS primary, pykrx fallback."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.trading.competition.replay import data_provider
from src.trading.competition.replay.calendar import resolve_replay_dates_with_meta


class ReplayDataProviderTests(unittest.TestCase):
    def test_trading_dates_kis_primary(self) -> None:
        with patch.object(data_provider, "_kis_ready", return_value=True):
            with patch.object(
                data_provider,
                "_kis_daily_bars",
                return_value=[
                    {"date": "20241210", "close": 70000, "open": 69000, "tv": 1},
                    {"date": "20241211", "close": 71000, "open": 70000, "tv": 1},
                    {"date": "20241212", "close": 72000, "open": 71000, "tv": 1},
                ],
            ):
                with patch.object(data_provider, "_pykrx_session_dates", return_value=([], [])):
                    result = data_provider.list_trading_dates_result("20241210", "20241212")
        self.assertTrue(result["ok"])
        self.assertEqual(result["dates"], ["20241210", "20241211", "20241212"])
        self.assertEqual(result["primary_source"], "kis_daily_chart")

    def test_trading_dates_both_fail(self) -> None:
        with patch.object(data_provider, "_kis_session_dates", return_value=([], ["kis:empty"])):
            with patch.object(data_provider, "_pykrx_session_dates", return_value=([], ["pykrx:fail"])):
                result = data_provider.list_trading_dates_result("20241210", "20241216")
        self.assertFalse(result["ok"])
        self.assertEqual(result["dates"], [])
        self.assertEqual(result["error"], "trading_calendar_unavailable")

    def test_pykrx_ohlcv_skipped_without_krx_creds(self) -> None:
        with patch.object(data_provider, "_kis_ready", return_value=False):
            with patch(
                "src.trading.competition.replay.pykrx_safe.krx_credentials_configured",
                return_value=False,
            ):
                mapped, source, errors = data_provider._load_ticker_ohlcv_map(
                    "005930", "20260101", "20260102"
                )
        self.assertEqual(mapped, {})
        self.assertIsNone(source)
        self.assertTrue(any("krx_credentials_missing" in e for e in errors))

    def test_short_5days_resolve_uses_provider(self) -> None:
        with patch(
            "src.trading.competition.replay.calendar.list_trading_dates_result",
            return_value={
                "ok": True,
                "dates": ["20241210", "20241211", "20241212", "20241213", "20241216"],
                "primary_source": "kis_daily_chart",
                "errors": [],
            },
        ):
            dates, meta = resolve_replay_dates_with_meta("short_5days", "20241210")
        self.assertEqual(len(dates), 5)
        self.assertTrue(meta["ok"])


if __name__ == "__main__":
    unittest.main()
