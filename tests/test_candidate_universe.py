"""MVP 4 — 후보군·우선주 제외·로그 집계 테스트."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.weekly_watchlist_update.candidate_report import (
    build_candidate_slack_text,
    build_scan_payload,
    write_candidate_outputs,
)
from agents.weekly_watchlist_update.candidate_scanner import (
    CandidateScanResult,
    DEFAULT_SCAN_LIMIT,
    format_candidate_scan_log_lines,
    format_candidate_scan_summary_line,
    format_scan_progress_line,
    format_scan_skip_line,
    run_candidate_scan,
)
from tests.test_candidate_scanner import _ohlcv_rows
from agents.weekly_watchlist_update.candidate_universe import (
    SCAN_SECTOR_PRIORITY,
    candidate_pool_stats,
    candidate_universe_size,
    is_preferred_stock,
    iter_candidate_entries,
    list_candidate_entries,
)


class TestPreferredStock(unittest.TestCase):
    def test_name_ends_with_woo(self):
        self.assertTrue(is_preferred_stock("일진전기우", "103590"))
        self.assertTrue(is_preferred_stock("삼성전기우", "009155"))

    def test_false_positive_daewoo(self):
        self.assertFalse(is_preferred_stock("대우", "000150"))

    def test_known_preferred_ticker(self):
        self.assertTrue(is_preferred_stock("아무이름", "103595"))

    def test_short_name_not_preferred(self):
        self.assertFalse(is_preferred_stock("우", "999999"))

    def test_universe_excludes_preferred(self):
        tickers = {e["ticker"] for e in iter_candidate_entries()}
        self.assertNotIn("103595", tickers)
        for entry in iter_candidate_entries():
            self.assertFalse(
                is_preferred_stock(entry["name"], entry["ticker"]),
                msg=entry["name"],
            )


class TestScanLimitAndPriority(unittest.TestCase):
    def test_default_scan_limit_constant(self):
        self.assertEqual(DEFAULT_SCAN_LIMIT, 60)

    def test_list_candidate_entries_respects_limit(self):
        full = list_candidate_entries()
        limited = list_candidate_entries(scan_limit=10)
        self.assertEqual(len(limited), 10)
        self.assertLess(len(limited), len(full))

    def test_priority_sectors_first(self):
        limited = list_candidate_entries(scan_limit=5)
        self.assertGreater(len(limited), 0)
        self.assertEqual(limited[0]["sector_name"], SCAN_SECTOR_PRIORITY[0])

    def test_scan_limit_stops_pykrx_calls(self):
        entries = [
            {
                "sector_name": "반도체 장비",
                "name": f"종목{i}",
                "ticker": f"10000{i}",
                "symbol": f"종목{i}",
            }
            for i in range(5)
        ]

        with patch(
            "agents.weekly_watchlist_update.candidate_scanner.list_candidate_entries",
            return_value=entries[:2],
        ):
            with patch(
                "agents.weekly_watchlist_update.candidate_scanner._fetch_ohlcv_with_timeout",
                return_value=([], {}),
            ) as fetch_mock:
                with patch(
                    "agents.weekly_watchlist_update.candidate_scanner.candidate_pool_stats",
                    return_value={
                        "pool_total": 5,
                        "excluded_watchlist": 0,
                        "excluded_large_caps": 0,
                        "excluded_preferred": 0,
                        "pool_scan_target": 5,
                    },
                ):
                    scan = run_candidate_scan(
                        as_of_date="2026-05-21",
                        news_by_ticker={},
                        scan_limit=2,
                        save_daily_scan_file=False,
                    )

        self.assertEqual(scan.scanned, 2)
        self.assertEqual(fetch_mock.call_count, 2)
        self.assertEqual(scan.scan_limit, 2)


class TestProgressLogFormat(unittest.TestCase):
    def test_progress_line_format(self):
        line = format_scan_progress_line(12, 60, "원익IPS", "240810")
        self.assertEqual(line, "[CANDIDATES] scanning 12/60 원익IPS(240810)")
        self.assertRegex(line, r"^\[CANDIDATES\] scanning \d+/\d+ .+\(\d{6}\)$")

    def test_skip_line_format(self):
        line = format_scan_skip_line("FM", "037830")
        self.assertEqual(line, "[CANDIDATES] skip missing/timeout: FM(037830)")

    def test_summary_line_format(self):
        scan = CandidateScanResult(as_of_date="2026-05-21", scanned=60, skipped=3)
        scan.candidates = [{}, {}, {}, {}, {}]
        scan.slack_yellow = [{}]
        scan.slack_red = [{}]
        line = format_candidate_scan_summary_line(scan)
        self.assertEqual(
            line,
            "[CANDIDATES] scanned=60 skipped=3 json=5 slack=🟢0 🟡1 🔴1",
        )


class TestPoolStatsAndLogs(unittest.TestCase):
    def test_pool_stats_fields(self):
        stats = candidate_pool_stats()
        self.assertIn("pool_total", stats)
        self.assertIn("excluded_watchlist", stats)
        self.assertIn("excluded_large_caps", stats)
        self.assertIn("excluded_preferred", stats)
        self.assertIn("pool_scan_target", stats)
        self.assertEqual(
            stats["pool_scan_target"],
            candidate_universe_size(),
        )

    def test_log_lines_separate_pool_and_scan(self):
        scan = CandidateScanResult(
            as_of_date="2026-05-21",
            pool_total=150,
            pool_scan_target=154,
            scan_limit=60,
            excluded_watchlist=25,
            excluded_large_caps=6,
            excluded_preferred=1,
            scanned=60,
            skipped=3,
            missing_ohlcv=3,
        )
        scan.candidates = [{"ticker": "100001"}]
        lines = format_candidate_scan_log_lines(scan)
        joined = "\n".join(lines)
        self.assertIn("pool_total=150", joined)
        self.assertIn("scan_limit=60", joined)
        self.assertIn("scanned=60 skipped=3 json=1", joined)
        self.assertIn("slack=🟢0 🟡0 🔴0", joined)
        self.assertIn("missing_ohlcv=3", joined)
        self.assertIn("excluded_preferred=1", joined)


class TestMissingOhlcvExclusion(unittest.TestCase):
    def test_missing_not_in_json_or_slack(self):
        entry = {
            "sector_name": "반도체 소재",
            "name": "노데이터",
            "ticker": "888888",
            "symbol": "노데이터",
        }
        good = {
            "sector_name": "AI 인프라",
            "name": "정상후보",
            "ticker": "777777",
            "symbol": "정상후보",
        }

        def fake_fetch(ticker, **kwargs):
            if ticker.zfill(6) == "888888":
                return [], {}
            return _ohlcv_rows(), {}

        with patch(
            "agents.weekly_watchlist_update.candidate_scanner.list_candidate_entries",
            return_value=[entry, good],
        ):
            with patch(
                "agents.weekly_watchlist_update.candidate_scanner._fetch_ohlcv_with_timeout",
                side_effect=fake_fetch,
            ):
                with patch(
                    "agents.weekly_watchlist_update.candidate_scanner.candidate_pool_stats",
                    return_value={
                        "pool_total": 2,
                        "excluded_watchlist": 0,
                        "excluded_large_caps": 0,
                        "excluded_preferred": 0,
                        "pool_scan_target": 2,
                    },
                ):
                    scan = run_candidate_scan(
                        as_of_date="2026-05-21",
                        news_by_ticker={},
                        save_daily_scan_file=False,
                    )

        self.assertEqual(scan.missing_ohlcv, 1)
        self.assertEqual(scan.skipped, 1)
        self.assertEqual(scan.scanned, 2)
        tickers = {c["ticker"] for c in scan.candidates}
        self.assertNotIn("888888", tickers)
        slack_tickers = {
            r["ticker"]
            for r in scan.slack_green + scan.slack_yellow + scan.slack_red
        }
        self.assertNotIn("888888", slack_tickers)

        payload = build_scan_payload(scan)
        self.assertEqual(payload["stats"]["missing_ohlcv"], 1)
        all_json_tickers = {c["ticker"] for c in payload["candidates"]}
        self.assertNotIn("888888", all_json_tickers)

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "agents.weekly_watchlist_update.candidate_report.SCAN_DIR",
                Path(tmp),
            ):
                path = write_candidate_outputs(scan)
            assert path is not None
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved_tickers = {c["ticker"] for c in saved["candidates"]}
            self.assertNotIn("888888", saved_tickers)

        text = build_candidate_slack_text(scan)
        self.assertNotIn("노데이터", text)


if __name__ == "__main__":
    unittest.main()
