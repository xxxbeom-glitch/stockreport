# -*- coding: utf-8 -*-
"""REPLAY eligible universe build — KIS/static without KRX credentials."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.trading.competition.replay import universe_replay as ur
from src.trading.competition.replay.snapshot_builder import build_close_snapshot


class ReplayUniverseBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self._preflight_patch = patch(
            "data.kis_client.preflight_kis_auth",
            return_value={"ok": True, "token_issue_calls": 1},
        )
        self._preflight_patch.start()

    def tearDown(self) -> None:
        self._preflight_patch.stop()
        from data import kis_client as kc

        kc.reset_kis_auth_state(clear_token=True)

    def test_no_pykrx_when_krx_missing(self) -> None:
        with patch("src.trading.competition.replay.pykrx_safe.krx_credentials_configured", return_value=False):
            with patch.object(ur, "load_static_ticker_master", return_value=[]):
                with patch.object(ur, "collect_base_universe_kis_volume") as mock_kis:
                    mock_kis.return_value = (
                        [
                            {
                                "ticker": "005930",
                                "name": "삼성전자",
                                "market": "KOSPI",
                                "current_price_krw": 70000,
                                "avg_trading_value_20d_krw": 5_000_000_000,
                                "history_days_present": 20,
                                "data_sources": ["kis_volume_rank"],
                            }
                        ],
                        [],
                    )
                    def _mark_risk(records, **kwargs):
                        for rec in records:
                            rec["risk_check_status"] = "verified"
                            rec["risk_status"] = "normal"
                            rec["risk_exclude_new_entry"] = False
                        return len(records), 0

                    with patch.object(ur, "enrich_risk_from_kis", side_effect=_mark_risk):
                        eligible, counts = ur.build_eligible_universe_for_replay("20260109")
        mock_kis.assert_called_once()
        self.assertEqual(counts.base_universe_source, "kis_volume_rank")
        self.assertGreater(counts.final_eligible_universe_count, 0)

    def test_static_master_kis_enrich_no_pykrx_collect(self) -> None:
        master = [
            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "data_sources": ["static_master"]},
            {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "data_sources": ["static_master"]},
        ]
        with patch("src.trading.competition.replay.pykrx_safe.krx_credentials_configured", return_value=False):
            with patch.object(ur, "load_static_ticker_master", return_value=master):
                with patch("src.trading.competition.universe.collector.collect_all_stocks") as mock_pykrx:
                    with patch.object(ur, "enrich_records_for_trading_date", return_value=(2, [], 2)):
                        with patch.object(ur, "enrich_risk_from_kis", return_value=(2, 0)):
                            eligible, counts = ur.build_eligible_universe_for_replay("20260109")
        mock_pykrx.assert_not_called()
        self.assertEqual(counts.base_universe_source, "static_master")
        self.assertEqual(counts.base_universe_count, 2)

    def test_snapshot_empty_universe_returns_build_counts(self) -> None:
        with patch(
            "src.trading.competition.replay.snapshot_builder.build_eligible_universe_for_replay",
            return_value=([], ur.UniverseStageCounts(trading_date="20260109", base_universe_count=0)),
        ):
            snap = build_close_snapshot("20260109")
        self.assertFalse(snap["ok"])
        self.assertEqual(snap["error"], "eligible_universe_empty")
        self.assertEqual(snap["universe_build"]["base_universe_count"], 0)

    def test_enrich_targets_all_common_without_cap(self) -> None:
        records = [
            {"ticker": f"{i:06d}", "name": f"테스트{i}", "market": "KOSPI", "data_sources": []}
            for i in range(60)
        ]
        calls: list[str] = []

        def _fake_enrich(rec: dict[str, Any], trading_date: str, start: str) -> tuple[dict[str, Any], bool]:
            calls.append(str(rec["ticker"]))
            rec["current_price_krw"] = 50_000
            rec["avg_trading_value_20d_krw"] = 5_000_000_000
            return rec, True

        with patch("src.trading.competition.replay.data_provider._kis_ready", return_value=True):
            with patch.object(ur, "_enrich_one_record", side_effect=_fake_enrich):
                enriched, _, target_n = ur.enrich_records_for_trading_date(records, "20260109")
        self.assertEqual(target_n, 60)
        self.assertEqual(enriched, 60)
        self.assertEqual(len(calls), 60)

    def test_etf_excluded_before_kis_enrich(self) -> None:
        records = [
            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
            {"ticker": "069500", "name": "KODEX 200 ETF", "market": "KOSPI"},
        ]
        with patch("src.trading.competition.replay.data_provider._kis_ready", return_value=True):
            with patch.object(ur, "_enrich_one_record", return_value=({}, False)) as mock_one:
                _, _, target_n = ur.enrich_records_for_trading_date(records, "20260109")
        self.assertEqual(target_n, 1)
        self.assertEqual(mock_one.call_count, 1)

    def test_krx_env_false_skips_pykrx_in_collector(self) -> None:
        from src.trading.competition.universe import collector

        with patch.dict(os.environ, {"KRX_ID": "", "KRX_PW": ""}, clear=False):
            tickers, err = collector.list_market_tickers("KOSPI", "20260109")
        self.assertEqual(tickers, [])
        self.assertIn("krx_credentials_missing", err or "")


if __name__ == "__main__":
    unittest.main()
