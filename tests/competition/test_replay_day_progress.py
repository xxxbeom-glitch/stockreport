# -*- coding: utf-8
"""Trading-day internal ticker cursor resume for REPLAY."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.trading.competition.replay import universe_replay as ur
from src.trading.competition.replay.day_progress import (
    PHASE_OHLCV,
    clear_day_progress,
    is_record_ohlcv_enriched,
    load_day_progress,
    load_partial_day_records,
    save_day_progress,
)
from src.trading.competition.replay.campaign_resume import (
    find_run_for_trading_date,
    init_campaign_manifest,
    save_checkpoint,
    save_manifest,
)


class DayProgressHelpersTest(unittest.TestCase):
    def test_is_record_ohlcv_enriched(self) -> None:
        rec = {
            "current_price_krw": 70000,
            "data_sources": ["kis_historical"],
        }
        self.assertTrue(is_record_ohlcv_enriched(rec, "20260109"))

    def test_enrich_skips_already_enriched_tickers(self) -> None:
        records = [
            {
                "ticker": "005930",
                "name": "삼성",
                "market": "KOSPI",
                "current_price_krw": 70000,
                "data_sources": ["kis_historical"],
                "_ohlcv_enriched_date": "20260109",
            },
            {"ticker": "000660", "name": "SK", "market": "KOSPI", "data_sources": []},
        ]
        calls: list[str] = []

        def _fake(rec: dict, trading_date: str, start: str) -> tuple[dict, bool]:
            calls.append(str(rec["ticker"]))
            rec["current_price_krw"] = 100_000
            rec["data_sources"] = ["kis_historical"]
            return rec, True

        with mock.patch("src.trading.competition.replay.data_provider._kis_ready", return_value=True):
            with mock.patch.object(ur, "_enrich_one_record", side_effect=_fake):
                enriched, _, target, stopped, nidx = ur.enrich_records_for_trading_date(
                    records, "20260109", start_index=0
                )
        self.assertEqual(enriched, 2)
        self.assertEqual(calls, ["000660"])
        self.assertFalse(stopped)
        self.assertEqual(nidx, 2)

    def test_enrich_resumes_from_cursor_index(self) -> None:
        records = [
            {"ticker": f"{i:06d}", "name": f"T{i}", "market": "KOSPI", "data_sources": []}
            for i in range(5)
        ]
        for i in range(2):
            records[i]["current_price_krw"] = 1000
            records[i]["data_sources"] = ["kis_historical"]
            records[i]["_ohlcv_enriched_date"] = "20260109"

        calls: list[str] = []

        def _fake(rec: dict, trading_date: str, start: str) -> tuple[dict, bool]:
            calls.append(str(rec["ticker"]))
            rec["current_price_krw"] = 2000
            return rec, True

        with mock.patch("src.trading.competition.replay.data_provider._kis_ready", return_value=True):
            with mock.patch.object(ur, "_enrich_one_record", side_effect=_fake):
                enriched, _, target, stopped, nidx = ur.enrich_records_for_trading_date(
                    records, "20260109", start_index=2
                )
        self.assertEqual(enriched, 5)
        self.assertEqual(calls, ["000002", "000003", "000004"])
        self.assertEqual(nidx, 5)


class DayProgressCheckpointTest(unittest.TestCase):
    def test_save_and_load_partial_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            camps = Path(tmp) / "campaigns"
            cid = "month_test_dp"
            with mock.patch("src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT", camps):
                with mock.patch("src.trading.competition.replay.day_progress.camp_dir", lambda c: camps / c):
                    manifest = init_campaign_manifest(
                        campaign_id=cid,
                        replay_type="month",
                        planned_dates=["20260109"],
                        chunk_size=1,
                        period_start="20260109",
                        period_end="20260109",
                    )
                    save_manifest(cid, manifest)
                    save_checkpoint(
                        cid,
                        {
                            "campaign_id": cid,
                            "planned_trading_dates": ["20260109"],
                            "completed_dates": {},
                            "run_ids": [],
                            "accounts": None,
                        },
                    )
                    rows = [{"ticker": "005930", "current_price_krw": 1}]
                    save_day_progress(
                        cid,
                        {
                            "trading_date": "20260109",
                            "phase": PHASE_OHLCV,
                            "ohlcv_cursor_index": 10,
                            "risk_cursor_index": 0,
                        },
                        records=rows,
                    )
                    loaded = load_partial_day_records(cid, "20260109")
                    prog = load_day_progress(cid)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded[0]["ticker"], "005930")
            self.assertEqual(prog.get("ohlcv_cursor_index"), 10)

    def test_find_run_returns_none_when_day_in_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            camps = Path(tmp) / "campaigns"
            cid = "month_dp_run"
            with mock.patch("src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT", camps):
                save_manifest(
                    cid,
                    {
                        "campaign_id": cid,
                        "planned_trading_dates": ["20260109"],
                        "completed_dates": {},
                    },
                )
                save_checkpoint(
                    cid,
                    {
                        "campaign_id": cid,
                        "planned_trading_dates": ["20260109"],
                        "completed_dates": {},
                        "run_ids": [],
                        "day_in_progress": {"trading_date": "20260109", "phase": PHASE_OHLCV},
                    },
                )
                hit = find_run_for_trading_date(cid, "20260109")
            self.assertIsNone(hit)


class StagePagesArtifactTest(unittest.TestCase):
    def test_staging_includes_dashboard_excludes_src(self) -> None:
        import sys

        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from scripts.stage_replay_pages_artifact import stage_pages_artifact

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pages"
            result = stage_pages_artifact(out)
            self.assertTrue((out / "index.html").is_file())
            self.assertTrue((out / "template" / "dashboard_desktop" / "index.html").is_file())
            self.assertFalse((out / "src").exists())
            self.assertFalse((out / "tests").exists())
            self.assertIn("index.html", result["copied"])


if __name__ == "__main__":
    unittest.main()
