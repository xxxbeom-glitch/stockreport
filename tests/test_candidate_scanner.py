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
    CandidateScanResult,
    build_candidate_caution,
    build_candidate_reason,
    compute_distance_pct,
    distance_band,
    effective_slack_tier,
    enrich_distance_fields,
    format_candidate_scan_log_lines,
    is_excluded_large_cap,
    partition_slack_display,
    score_candidate,
)
from agents.weekly_watchlist_update.candidate_universe import (
    EXCLUDED_LARGE_CAPS,
    candidate_universe_size,
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


def _row_with_zone(
    *,
    name: str = "테스트",
    ticker: str = "100099",
    current: int,
    lo: int,
    hi: int,
    tier: str = "green",
    score: int = 75,
) -> dict:
    row = {
        "name": name,
        "ticker": ticker,
        "sector_name": "반도체 소재",
        "current_price": current,
        "current_price_fmt": f"{current:,}원",
        "return_5d_pct": 3.0,
        "tv_increase": True,
        "near_high": True,
        "latest_trading_value": 2_000_000_000,
        "entry_low": lo,
        "entry_high": hi,
        "entry_range": f"{lo:,}원 ~ {hi:,}원",
        "tier": tier,
        "score": score,
        "has_news": False,
        "has_dart": False,
    }
    enrich_distance_fields(row)
    row["ai_reason"] = build_candidate_reason(row)
    row["ai_cancel_condition"] = build_candidate_caution(row)
    return row


class TestUniverseSize(unittest.TestCase):
    def test_pool_size_at_least_100_after_exclusions(self):
        self.assertGreaterEqual(candidate_universe_size(), 100)
        self.assertLessEqual(candidate_universe_size(), 200)

    def test_large_caps_not_in_iterable_universe(self):
        for entry in iter_candidate_entries():
            self.assertNotIn(entry["ticker"], EXCLUDED_LARGE_CAPS)


class TestWatchlistExclusion(unittest.TestCase):
    def test_universe_excludes_watchlist_tickers(self):
        wl = watchlist_ticker_set()
        for entry in iter_candidate_entries(exclude_watchlist=True):
            self.assertNotIn(entry["ticker"], wl)

    def test_pool_stats_matches_scan_target(self):
        from agents.weekly_watchlist_update.candidate_universe import (
            candidate_pool_stats,
        )

        stats = candidate_pool_stats()
        self.assertEqual(stats["pool_scan_target"], candidate_universe_size())
        self.assertGreaterEqual(stats["pool_total"], stats["pool_scan_target"])


class TestLargeCapExclusion(unittest.TestCase):
    def test_samsung_sk_hynix_excluded_by_default(self):
        self.assertTrue(is_excluded_large_cap("005930"))
        self.assertTrue(is_excluded_large_cap("000660"))
        from agents.weekly_watchlist_update.candidate_universe import (
            EXCLUDED_LARGE_CAPS as LC,
            candidate_pool_stats,
        )

        self.assertIn("005930", LC)
        for entry in iter_candidate_entries():
            self.assertNotIn(entry["ticker"], LC)
        self.assertEqual(
            {e["ticker"] for e in iter_candidate_entries()} & LC,
            set(),
        )


class TestDistanceFilter(unittest.TestCase):
    def test_distance_bands(self):
        self.assertEqual(distance_band(5.0), "ok")
        self.assertEqual(distance_band(10.0), "red_only")
        self.assertEqual(distance_band(13.0), "exclude")

    def test_distance_over_12_pct_slack_excluded(self):
        row = _row_with_zone(current=100_000, lo=80_000, hi=82_000, tier="green")
        self.assertGreater(row["distance_pct"], 12.0)
        self.assertIsNone(effective_slack_tier(row))

    def test_distance_within_8_pct_slack_green(self):
        row = _row_with_zone(current=50_500, lo=49_000, hi=51_000, tier="green")
        self.assertLessEqual(row["distance_pct"], 8.0)
        self.assertEqual(effective_slack_tier(row), "green")


class TestSlackLimits(unittest.TestCase):
    def test_red_max_one_and_overflow_note(self):
        scored = [
            _row_with_zone(
                name=f"패스{i}",
                ticker=f"20000{i}",
                current=50_000,
                lo=48_000,
                hi=49_000,
                tier="red",
                score=40 - i,
            )
            for i in range(3)
        ]
        _, _, slack_red, overflow = partition_slack_display(scored)
        self.assertEqual(len(slack_red), 1)
        self.assertEqual(overflow, 2)

    def test_new_candidate_count_green_yellow_only(self):
        scan = CandidateScanResult(as_of_date="2026-05-21")
        scan.slack_green = [
            _row_with_zone(current=50_000, lo=49_000, hi=51_000, name="알파", ticker="100001")
        ]
        scan.slack_yellow = [
            _row_with_zone(
                current=50_200,
                lo=49_000,
                hi=51_000,
                name="베타",
                ticker="100002",
                tier="yellow",
                score=55,
            )
        ]
        scan.slack_red = [
            _row_with_zone(
                current=50_000,
                lo=48_000,
                hi=49_000,
                name="감마",
                ticker="100003",
                tier="red",
                score=40,
            )
        ]
        scan.slack_red_overflow = 2
        text = build_candidate_slack_text(scan)
        self.assertIn("새 후보: 2개", text)
        self.assertNotIn("새 후보: 3개", text)
        self.assertIn("_그 외 패스 2개는 JSON에 저장_", text)
        self.assertEqual(text.count("🔴 오늘은 패스"), 1)
        self.assertEqual(text.count("• 감마"), 1)

    def test_empty_slack_message(self):
        scan = CandidateScanResult(as_of_date="2026-05-21")
        text = build_candidate_slack_text(scan)
        self.assertIn("새 후보: 0개", text)
        self.assertIn("오늘은 새로 볼 만한 종목이 뚜렷하지 않습니다", text)
        self.assertIn("기존 관심종목만 확인", text)
        self.assertEqual(validate_slack_text(text), [])


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
        self.assertIn("distance_pct", green)

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

        short_reason = build_candidate_reason(row, slack_pass=True)
        self.assertIn("볼 구간과 너무 멀어", short_reason)


class TestPersistence(unittest.TestCase):
    def test_write_json(self):
        scan = CandidateScanResult(as_of_date="2026-05-21")
        path = write_candidate_outputs(scan)
        self.assertIsNotNone(path)
        assert path is not None
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
