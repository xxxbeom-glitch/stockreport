"""MVP 4 — 신규 후보 스캔 테스트."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from agents.weekly_watchlist_update.candidate_report import (
    build_candidate_slack_text,
    validate_slack_text,
    write_candidate_outputs,
)
from agents.weekly_watchlist_update.candidate_scanner import (
    TIER_GREEN_MIN,
    TIER_RED_MIN,
    TIER_YELLOW_MIN,
    build_candidate_caution,
    build_candidate_reason,
    run_candidate_scan,
    score_candidate,
)
from agents.weekly_watchlist_update.candidate_universe import (
    iter_candidate_entries,
)
from data.kr_watchlist import watchlist_ticker_set


def _ohlcv_rows(
    *,
    return_pct: float = 3.0,
    tv_base: float = 2_000_000_000,
    tv_recent_mult: float = 1.2,
    near_high: bool = True,
) -> list[dict]:
    start = 10000.0
    end = start * (1 + return_pct / 100.0)
    rows = []
    for i in range(8):
        close = start + (end - start) * (i / 7)
        high = close * (1.01 if near_high and i >= 6 else 1.0)
        tv = tv_base * (tv_recent_mult if i >= 6 else 1.0)
        rows.append(
            {
                "date": f"2026-05-{10 + i:02d}",
                "open": close,
                "high": high,
                "low": close * 0.99,
                "close": close,
                "volume": 100000,
                "trading_value": tv,
            }
        )
    rows[-1]["close"] = end
    rows[-1]["high"] = end * 1.005
    return rows


class TestWatchlistExclusion(unittest.TestCase):
    def test_universe_excludes_watchlist_tickers(self):
        wl = watchlist_ticker_set()
        for entry in iter_candidate_entries(exclude_watchlist=True):
            self.assertNotIn(entry["ticker"], wl)

    def test_scan_skips_watchlist_ticker(self):
        wl_ticker = next(iter(watchlist_ticker_set()))
        fake_rows = _ohlcv_rows()

        def fake_fetch(ticker, **kwargs):
            if ticker.zfill(6) == wl_ticker:
                return fake_rows, {}
            return [], {}

        with patch(
            "agents.weekly_watchlist_update.candidate_scanner.fetch_ohlcv_history",
            side_effect=fake_fetch,
        ):
            with patch(
                "agents.weekly_watchlist_update.candidate_scanner.iter_candidate_entries",
                return_value=iter(
                    [
                        {
                            "sector_name": "반도체 소재",
                            "name": "WL종목",
                            "ticker": wl_ticker,
                            "symbol": "WL종목",
                        },
                        {
                            "sector_name": "AI 인프라",
                            "name": "테스트후보",
                            "ticker": "999999",
                            "symbol": "테스트후보",
                        },
                    ]
                ),
            ):
                scan = run_candidate_scan(as_of_date="2026-05-21", news_by_ticker={})

        tickers = {c["ticker"] for c in scan.candidates}
        self.assertNotIn(wl_ticker, tickers)


class TestScoring(unittest.TestCase):
    def test_high_score_ranks_first(self):
        low = score_candidate(
            {"name": "A", "ticker": "111111", "sector_name": "반도체 소재"},
            {
                "current_price": 10000,
                "return_5d_pct": 1.0,
                "tv_increase": False,
                "near_high": False,
                "latest_trading_value": 1_000_000_000,
                "day_high": 10000,
                "day_low": 9500,
                "prev_close": 9900,
            },
        )
        high = score_candidate(
            {"name": "B", "ticker": "222222", "sector_name": "반도체 소재"},
            {
                "current_price": 10000,
                "return_5d_pct": 5.0,
                "tv_increase": True,
                "near_high": True,
                "latest_trading_value": 2_000_000_000,
                "day_high": 10000,
                "day_low": 9500,
                "prev_close": 9900,
            },
            has_news=True,
            has_dart=True,
        )
        self.assertGreater(high["score"], low["score"])

    def test_tier_thresholds(self):
        green = score_candidate(
            {"name": "G", "ticker": "333333", "sector_name": "AI 인프라"},
            {
                "current_price": 50000,
                "return_5d_pct": 4,
                "tv_increase": True,
                "near_high": True,
                "latest_trading_value": 3_000_000_000,
                "day_high": 50000,
                "day_low": 48000,
                "prev_close": 49000,
            },
            has_news=True,
            has_dart=True,
        )
        self.assertGreaterEqual(green["score"], TIER_GREEN_MIN)
        self.assertEqual(green["tier"], "green")

        mid = score_candidate(
            {"name": "Y", "ticker": "444444", "sector_name": "AI 인프라"},
            {
                "current_price": 50000,
                "return_5d_pct": 2,
                "tv_increase": True,
                "near_high": False,
                "latest_trading_value": 3_000_000_000,
                "day_high": 50000,
                "day_low": 48000,
                "prev_close": 49000,
            },
            has_news=True,
        )
        self.assertGreaterEqual(mid["score"], TIER_YELLOW_MIN)
        self.assertLess(mid["score"], TIER_GREEN_MIN)
        self.assertEqual(mid["tier"], "yellow")

        weak = score_candidate(
            {"name": "R", "ticker": "555555", "sector_name": "AI 인프라"},
            {
                "current_price": 50000,
                "return_5d_pct": 2,
                "tv_increase": False,
                "near_high": True,
                "latest_trading_value": 3_000_000_000,
                "day_high": 50000,
                "day_low": 48000,
                "prev_close": 49000,
            },
        )
        self.assertGreaterEqual(weak["score"], TIER_RED_MIN)
        self.assertLess(weak["score"], TIER_YELLOW_MIN)
        self.assertEqual(weak["tier"], "red")


class TestSlackOutput(unittest.TestCase):
    def test_slack_tier_sections(self):
        from agents.weekly_watchlist_update.candidate_scanner import CandidateScanResult

        scan = CandidateScanResult(as_of_date="2026-05-21")
        scan.green = [
            score_candidate(
                {"name": "알파", "ticker": "100001", "sector_name": "반도체 소재"},
                {
                    "current_price": 62000,
                    "return_5d_pct": 5,
                    "tv_increase": True,
                    "near_high": True,
                    "latest_trading_value": 5_000_000_000,
                    "day_high": 62000,
                    "day_low": 60000,
                    "prev_close": 61000,
                },
                has_news=True,
            )
        ]
        scan.yellow = [
            score_candidate(
                {"name": "베타", "ticker": "100002", "sector_name": "반도체 부품"},
                {
                    "current_price": 146400,
                    "return_5d_pct": 2,
                    "tv_increase": True,
                    "near_high": False,
                    "latest_trading_value": 4_000_000_000,
                    "day_high": 146400,
                    "day_low": 140000,
                    "prev_close": 145000,
                },
            )
        ]
        scan.red = [
            score_candidate(
                {"name": "감마", "ticker": "100003", "sector_name": "방산·우주"},
                {
                    "current_price": 80000,
                    "return_5d_pct": 1,
                    "tv_increase": False,
                    "near_high": False,
                    "latest_trading_value": 3_000_000_000,
                    "day_high": 80000,
                    "day_low": 78000,
                    "prev_close": 79000,
                },
            )
        ]
        scan.candidates = scan.green + scan.yellow + scan.red
        text = build_candidate_slack_text(scan)
        self.assertIn("🟢 지금 볼만함", text)
        self.assertIn("🟡 조금 기다림", text)
        self.assertIn("🔴 오늘은 패스", text)
        self.assertIn("알파", text)
        self.assertEqual(validate_slack_text(text), [])

    def test_empty_candidates_message(self):
        from agents.weekly_watchlist_update.candidate_scanner import CandidateScanResult

        scan = CandidateScanResult(as_of_date="2026-05-21")
        text = build_candidate_slack_text(scan)
        self.assertIn("오늘 새 후보 없음", text)
        self.assertEqual(validate_slack_text(text), [])

    def test_reason_and_caution_no_forbidden_words(self):
        row = score_candidate(
            {"name": "테스트", "ticker": "100004", "sector_name": "전력/에너지"},
            {
                "current_price": 10000,
                "return_5d_pct": 3,
                "tv_increase": True,
                "near_high": True,
                "latest_trading_value": 2_000_000_000,
                "day_high": 10000,
                "day_low": 9500,
                "prev_close": 9800,
            },
            has_news=True,
        )
        reason = build_candidate_reason(row)
        caution = build_candidate_caution(row)
        for text in (reason, caution):
            self.assertNotIn("추천", text)
            self.assertNotIn("진입", text)
            if "매수" in text:
                self.assertIn("외국인 매수", text)


class TestPersistence(unittest.TestCase):
    def test_write_json(self):
        from agents.weekly_watchlist_update.candidate_scanner import CandidateScanResult

        scan = CandidateScanResult(as_of_date="2026-05-21")
        path = write_candidate_outputs(scan)
        self.assertIsNotNone(path)
        assert path is not None
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
