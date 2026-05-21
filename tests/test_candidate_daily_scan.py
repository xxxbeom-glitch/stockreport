"""MVP 4-3 — daily_scan 누적·trend_score·Slack 흐름 문구 테스트."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.weekly_watchlist_update.candidate_daily_scan import (
    TREND_MULTI_DAY_CANDIDATE,
    TREND_ONE_DAY_SPIKE,
    apply_trend_to_candidates,
    build_trend_candidate_reason,
    compute_trend_score,
    enrich_row_with_trend,
    is_candidate_day_record,
    load_recent_candidate_scans,
    partition_slack_by_trend,
    row_to_daily_record,
    save_daily_scan,
)
from agents.weekly_watchlist_update.candidate_report import build_candidate_slack_text
from agents.weekly_watchlist_update.candidate_scanner import (
    CandidateScanResult,
    enrich_distance_fields,
    run_candidate_scan,
)
from tests.test_candidate_scanner import _ohlcv_rows, _row_with_zone


def _daily_rec(
    *,
    date: str,
    ticker: str = "240810",
    name: str = "원익IPS",
    score: int = 55,
    tier: str = "yellow",
    tv_up: bool = True,
    ret: float = 2.0,
    news: bool = False,
) -> dict:
    return {
        "date": date,
        "ticker": ticker,
        "name": name,
        "sector": "반도체 장비",
        "current_price": 50000,
        "return_5d": ret,
        "trading_value": 2_000_000_000,
        "trading_value_change": tv_up,
        "near_high": True,
        "has_news": news,
        "has_dart": False,
        "score": score,
        "tier": tier,
        "agent_votes": None,
        "vote_summary": None,
        "final_opinion": None,
    }


class TestTrendScore(unittest.TestCase):
    def test_three_day_candidate_bonus(self):
        hist = [
            _daily_rec(date=f"2026-05-{17 + i}", score=50 + i, tier="yellow")
            for i in range(3)
        ]
        meta = compute_trend_score(hist, window_days=5)
        self.assertGreaterEqual(meta["trend_candidate_days"], 3)
        self.assertGreaterEqual(meta["trend_score"], TREND_MULTI_DAY_CANDIDATE)

    def test_one_day_spike_penalty(self):
        meta = compute_trend_score([_daily_rec(date="2026-05-21")], window_days=5)
        self.assertTrue(meta["one_day_spike"])
        self.assertIn(TREND_ONE_DAY_SPIKE, meta["trend_breakdown"].values())

    def test_final_score_sort(self):
        rows = [
            {"ticker": "111111", "name": "A", "score": 40, "tier": "yellow"},
            {"ticker": "222222", "name": "B", "score": 70, "tier": "green"},
        ]
        history = {
            "111111": [_daily_rec(date="2026-05-19", ticker="111111", score=45)] * 3,
            "222222": [_daily_rec(date="2026-05-19", ticker="222222", score=60)],
        }
        enriched = apply_trend_to_candidates(
            rows, history, today_date="2026-05-21", window_days=5
        )
        self.assertGreater(
            enriched[0]["final_candidate_score"],
            enriched[1]["final_candidate_score"],
        )

    def test_missing_days_no_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            save_daily_scan("2026-05-20", [_daily_rec(date="2026-05-20")], scan_dir=base)
            loaded = load_recent_candidate_scans(
                days=5, end_date="2026-05-21", scan_dir=base
            )
        self.assertIn("240810", loaded)
        self.assertEqual(len(loaded["240810"]), 1)


class TestSlackTrendCopy(unittest.TestCase):
    def test_green_reason_mentions_multi_day_flow(self):
        row = {
            "slack_tier": "green",
            "trend_score": 40,
            "one_day_spike": False,
        }
        text = build_trend_candidate_reason(row)
        self.assertIn("최근 며칠", text)
        self.assertIn("거래가 꾸준히", text)

    def test_yellow_reason_short_trend(self):
        row = {"slack_tier": "yellow", "trend_score": 5}
        text = build_trend_candidate_reason(row)
        self.assertIn("최근 흐름은 아직 짧아", text)

    def test_one_day_spike_reason(self):
        row = {"slack_tier": "red", "one_day_spike": True}
        text = build_trend_candidate_reason(row)
        self.assertIn("하루만 강하게", text)

    def test_slack_message_includes_trend_phrase(self):
        row = _row_with_zone(
            current=50_000,
            lo=49_000,
            hi=51_000,
            name="멀티데이",
            ticker="240810",
            tier="green",
            score=75,
        )
        enrich_distance_fields(row)
        row.update(
            {
                "today_score": 75,
                "trend_score": 45,
                "final_candidate_score": 120,
                "slack_tier": "green",
                "slack_pass_short": False,
                "one_day_spike": False,
                "ai_reason": build_trend_candidate_reason(
                    {"slack_tier": "green", "trend_score": 45, "one_day_spike": False}
                ),
                "ai_cancel_condition": "살짝 눌리는지 보는 게 좋습니다.",
                "agent_check_line": "체크: 가격 ✅ / 거래 ✅ / 뉴스 △ / 위험 괜찮음",
            }
        )
        scan = CandidateScanResult(as_of_date="2026-05-21")
        scan.slack_green = [row]
        text = build_candidate_slack_text(scan)
        self.assertIn("최근 며칠", text)


class TestScanLimitWithDaily(unittest.TestCase):
    def test_run_respects_limit_and_saves_daily(self):
        entries = [
            {
                "sector_name": "반도체 장비",
                "name": f"종목{i}",
                "ticker": f"30000{i}",
                "symbol": f"종목{i}",
            }
            for i in range(4)
        ]

        with tempfile.TemporaryDirectory() as tmp:
            scan_dir = Path(tmp) / "daily_scan"
            with patch(
                "agents.weekly_watchlist_update.candidate_scanner.list_candidate_entries",
                return_value=entries[:2],
            ):
                with patch(
                    "agents.weekly_watchlist_update.candidate_scanner._fetch_ohlcv_with_timeout",
                    return_value=(_ohlcv_rows(), {}),
                ):
                    with patch(
                        "agents.weekly_watchlist_update.candidate_scanner.candidate_pool_stats",
                        return_value={
                            "pool_total": 4,
                            "excluded_watchlist": 0,
                            "excluded_large_caps": 0,
                            "excluded_preferred": 0,
                            "pool_scan_target": 4,
                        },
                    ):
                        with patch(
                            "agents.weekly_watchlist_update.candidate_daily_scan.save_daily_scan",
                            wraps=save_daily_scan,
                        ) as save_mock:
                            scan = run_candidate_scan(
                                as_of_date="2026-05-21",
                                news_by_ticker={},
                                scan_limit=2,
                                candidate_days=5,
                                save_daily_scan_file=True,
                            )
                            save_mock.assert_called_once()

            self.assertEqual(scan.scanned, 2)
            self.assertIsNotNone(scan.daily_scan_path)

    def test_is_candidate_day_record(self):
        self.assertTrue(is_candidate_day_record({"tier": "yellow", "score": 40}))
        self.assertFalse(is_candidate_day_record({"tier": "exclude", "score": 10}))


class TestPartitionByTrend(unittest.TestCase):
    def test_partition_uses_slack_tier(self):
        rows = [
            {
                "name": "G",
                "ticker": "100001",
                "final_candidate_score": 100,
                "slack_tier": "green",
                "slack_pass_short": False,
            },
            {
                "name": "Y",
                "ticker": "100002",
                "final_candidate_score": 80,
                "slack_tier": "yellow",
                "slack_pass_short": False,
            },
        ]
        g, y, r, overflow = partition_slack_by_trend(rows)
        self.assertEqual(len(g), 1)
        self.assertEqual(len(y), 1)
        self.assertEqual(overflow, 0)


if __name__ == "__main__":
    unittest.main()
