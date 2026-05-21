"""주간 관심종목 MVP 단위 테스트."""

from __future__ import annotations

import unittest

from agents.weekly_watchlist_update.sector_mood import judge_weekly_sector_mood
from agents.weekly_watchlist_update.slack_history import aggregate_ticker_slack_stats
from agents.weekly_watchlist_update.weekly_metrics import (
    MARKET_HARD_OVERRIDES,
    _ohlcv_frame_to_rows,
    attach_sector_relative_strength,
    classify_data_status,
    compute_stock_metrics,
    resolve_pykrx_market,
)
from agents.weekly_watchlist_update.weekly_report import (
    SLACK_REVIEW_REMOVE_MAX,
    SLACK_SECTION_MAX,
    SLACK_STRONG_REMOVE_MAX,
    build_slack_text,
)
from agents.weekly_watchlist_update.weekly_review import (
    ACTION_DATA_CHECK,
    ACTION_REMOVE,
    ACTION_WEAKEN,
    REASON_CAUTION,
    REASON_REMOVE_MULTI,
    REMOVE_LEVEL_REVIEW,
    REMOVE_LEVEL_STRONG,
    REMOVE_MIN_SIGNALS,
    SEVERITY_LABEL_REVIEW,
    SEVERITY_LABEL_STRONG,
    classify_remove_level,
    count_remove_signals,
    is_remove_eligible,
    momentum_weak_count,
    rule_precheck,
    rule_only_judgment,
)


def _ohlcv(closes: list[float], tv: float = 1e9) -> list[dict]:
    rows = []
    for i, c in enumerate(closes):
        rows.append(
            {
                "date": f"2026-05-{10 + i:02d}",
                "open": c,
                "high": c * 1.02,
                "low": c * 0.98,
                "close": c,
                "volume": 1000,
                "trading_value": tv,
            }
        )
    return rows


class TestWeeklyMetrics(unittest.TestCase):
    def test_resolve_010620_hard_override_kospi(self):
        self.assertEqual(MARKET_HARD_OVERRIDES.get("010620"), "KOSPI")
        r = resolve_pykrx_market("010620")
        self.assertEqual(r["resolved_market"], "KOSPI")
        self.assertEqual(r["resolve_source"], "hard_override")

    def test_resolve_prefers_kospi_list_over_default(self):
        """목록에 없어도 기본값은 KOSDAQ이 아닌 KOSPI."""
        r = resolve_pykrx_market("999999", requested_market="KOSDAQ")
        if not r.get("in_kospi") and not r.get("in_kosdaq"):
            self.assertEqual(r["resolved_market"], "KOSDAQ")
            self.assertEqual(r["resolve_source"], "requested_fallback")

    def test_ohlcv_frame_without_trading_value_column(self):
        import pandas as pd

        frame = pd.DataFrame(
            {
                "시가": [100],
                "고가": [102],
                "저가": [98],
                "종가": [101],
                "거래량": [1000],
            },
            index=pd.to_datetime(["2026-05-20"]),
        )
        rows = _ohlcv_frame_to_rows(frame)
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0]["trading_value"], 0)

    def test_compute_returns_and_tv_growth(self):
        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 110, 112]
        row = compute_stock_metrics(
            {"ticker": "005930", "name": "삼성전자", "sector_name": "반도체"},
            _ohlcv(closes, tv=2e9),
            snapshot={"high_52": 120, "volume_ratio": 1.1},
            slack_stat={"recent_slack_sent_count": 2, "recent_candidate_count": 4},
        )
        self.assertEqual(row["ticker"], "005930")
        self.assertGreater(row["return_5d"], 0)
        self.assertGreater(row["tv_5d_avg"], 0)
        self.assertEqual(row["data_status"], "ok_10d")

    def test_classify_data_status(self):
        self.assertEqual(classify_data_status(12), "ok_10d")
        self.assertEqual(classify_data_status(7), "ok_5d")
        self.assertEqual(classify_data_status(3), "partial")
        self.assertEqual(classify_data_status(0), "missing_ohlcv")

    def test_sector_relative_strength_percentile(self):
        metrics = [
            {"sector": "A", "ticker": "000001", "return_5d": 5.0, "data_status": "ok_10d"},
            {"sector": "A", "ticker": "000002", "return_5d": -2.0, "data_status": "ok_10d"},
        ]
        out = attach_sector_relative_strength(metrics)
        scores = {r["ticker"]: r["sector_relative_strength"] for r in out}
        self.assertGreater(scores["000001"], scores["000002"])


class TestSlackHistory(unittest.TestCase):
    def test_aggregate_counts(self):
        records = [
            {"ticker": "005930", "sent": True, "slot": "0930"},
            {"ticker": "005930", "sent": False, "slot": "1050"},
            {"ticker": "000660", "sent": True, "slot": "0930"},
        ]
        stats = aggregate_ticker_slack_stats(records)
        self.assertEqual(stats["005930"]["recent_slack_sent_count"], 1)
        self.assertEqual(stats["005930"]["recent_candidate_count"], 2)


class TestWeeklyReview(unittest.TestCase):
    def test_rule_precheck_missing_ohlcv_is_data_check(self):
        row = {
            "sector": "반도체 소재",
            "return_5d": -10,
            "data_quality": "missing_ohlcv",
            "data_status": "missing_ohlcv",
        }
        hint = rule_precheck(row, {"반도체 소재": "weak"})
        self.assertEqual(hint["rule_action"], ACTION_DATA_CHECK)
        self.assertIn("OHLCV", hint["rule_reasons"][0])

    def test_rule_precheck_remove_on_weak_sector(self):
        row = {
            "sector": "반도체",
            "return_5d": -6,
            "tv_growth_5d_vs_10d": -0.2,
            "drawdown_from_recent_high": 15,
            "position_vs_52w_high": 0.7,
            "sector_relative_strength": 20,
            "data_quality": "ok",
            "data_status": "ok_10d",
            "recent_slack_sent_count": 0,
            "recent_candidate_count": 0,
        }
        n, flags = count_remove_signals(row, {"반도체": "weak"})
        self.assertGreaterEqual(n, REMOVE_MIN_SIGNALS)
        self.assertGreaterEqual(momentum_weak_count(flags), 2)
        self.assertTrue(is_remove_eligible(flags, row=row))
        hint = rule_precheck(row, {"반도체": "weak"})
        self.assertEqual(hint["rule_action"], ACTION_REMOVE)
        self.assertEqual(hint["reason_code"], REASON_REMOVE_MULTI)

    def test_structure_only_not_remove_without_momentum(self):
        """고점 조정·섹터 약세만으로는 remove 불가 (모멘텀 약세 2개 미만)."""
        row = {
            "sector": "방산·우주",
            "return_5d": 0,
            "tv_growth_5d_vs_10d": -0.03,
            "drawdown_from_recent_high": 14,
            "position_vs_52w_high": 0.75,
            "sector_relative_strength": 90,
            "data_status": "ok_10d",
        }
        n, flags = count_remove_signals(row, {"방산·우주": "weak"})
        self.assertGreaterEqual(n, 2)
        self.assertEqual(momentum_weak_count(flags), 0)
        self.assertFalse(is_remove_eligible(flags, row=row))
        hint = rule_precheck(row, {"방산·우주": "weak"})
        self.assertNotEqual(hint["rule_action"], ACTION_REMOVE)
        self.assertEqual(hint["reason_code"], REASON_CAUTION)

    def test_drawdown_alone_not_remove(self):
        """고점 조정+52주 위치만으로는 remove 금지 → caution."""
        row = {
            "sector": "2차전지",
            "return_5d": -1,
            "tv_growth_5d_vs_10d": 0.05,
            "drawdown_from_recent_high": 14,
            "position_vs_52w_high": 0.8,
            "sector_relative_strength": 45,
            "data_status": "ok_10d",
        }
        n, _ = count_remove_signals(row, {"2차전지": "neutral"})
        self.assertLess(n, REMOVE_MIN_SIGNALS)
        hint = rule_precheck(row, {"2차전지": "neutral"})
        self.assertNotEqual(hint["rule_action"], ACTION_REMOVE)
        self.assertEqual(hint["reason_code"], REASON_CAUTION)

    def test_remove_not_excessive_on_watchlist_like_batch(self):
        """중립~약한 메트릭 25종목에서 remove 과다 방지."""
        metrics = []
        for i in range(25):
            metrics.append(
                {
                    "ticker": f"{i:06d}",
                    "symbol": f"종목{i}",
                    "sector": "반도체" if i % 2 == 0 else "2차전지",
                    "return_5d": -4 + (i % 5),
                    "tv_growth_5d_vs_10d": -0.03 + (i % 3) * 0.02,
                    "drawdown_from_recent_high": 8 + (i % 4),
                    "position_vs_52w_high": 0.82 + (i % 5) * 0.02,
                    "sector_relative_strength": 38 + (i % 7),
                    "data_status": "ok_10d",
                    "recent_slack_sent_count": 0,
                    "recent_candidate_count": 0,
                }
            )
        mood = judge_weekly_sector_mood(metrics)
        j = rule_only_judgment(metrics, mood)
        remove_n = j["remove_count"]
        caution_n = j.get("caution_count", 0)
        self.assertLessEqual(remove_n, 7, f"remove={remove_n} caution={caution_n}")
        self.assertGreater(caution_n, 0)
        self.assertGreater(j["keep_count"], 0)

    def test_exception_remove_three_momentum_low_rs(self):
        """모멘텀 약세 3개 + RS 매우 낮음 — 신호 4개 미만이어도 remove."""
        row = {
            "sector": "반도체 소재",
            "return_5d": -5,
            "tv_growth_5d_vs_10d": -0.12,
            "drawdown_from_recent_high": 6,
            "position_vs_52w_high": 0.92,
            "sector_relative_strength": 25,
            "data_status": "ok_10d",
        }
        n, flags = count_remove_signals(row, {"반도체 소재": "neutral"})
        self.assertEqual(momentum_weak_count(flags), 3)
        self.assertLess(n, REMOVE_MIN_SIGNALS)
        self.assertTrue(is_remove_eligible(flags, row=row))
        hint = rule_precheck(row, {"반도체 소재": "neutral"})
        self.assertEqual(hint["rule_action"], ACTION_REMOVE)

    def test_basic_remove_four_signals_two_momentum(self):
        """신호 4개 + 모멘텀 2개 — 기본 remove 충족."""
        row = {
            "sector": "반도체",
            "return_5d": -5,
            "tv_growth_5d_vs_10d": -0.1,
            "drawdown_from_recent_high": 14,
            "position_vs_52w_high": 0.8,
            "sector_relative_strength": 50,
            "data_status": "ok_10d",
        }
        n, flags = count_remove_signals(row, {"반도체": "neutral"})
        self.assertGreaterEqual(n, REMOVE_MIN_SIGNALS)
        mom = momentum_weak_count(flags)
        self.assertEqual(mom, 2)
        self.assertTrue(is_remove_eligible(flags, row=row))
        level, label = classify_remove_level(
            remove_signal_count=n,
            momentum_weak_count=mom,
            priority_score=28,
        )
        self.assertEqual(level, REMOVE_LEVEL_REVIEW)
        self.assertEqual(label, SEVERITY_LABEL_REVIEW)
        hint = rule_precheck(row, {"반도체": "neutral"})
        self.assertEqual(hint["rule_action"], ACTION_REMOVE)
        self.assertEqual(hint["remove_level"], REMOVE_LEVEL_REVIEW)
        self.assertEqual(hint["severity_label"], SEVERITY_LABEL_REVIEW)

    def test_six_signals_three_momentum_is_strong_remove(self):
        """6신호/3모멘텀 — strong_remove."""
        row = {
            "sector": "반도체",
            "return_5d": -6,
            "tv_growth_5d_vs_10d": -0.2,
            "drawdown_from_recent_high": 15,
            "position_vs_52w_high": 0.7,
            "sector_relative_strength": 20,
            "data_status": "ok_10d",
        }
        n, flags = count_remove_signals(row, {"반도체": "weak"})
        mom = momentum_weak_count(flags)
        self.assertGreaterEqual(n, 5)
        self.assertGreaterEqual(mom, 3)
        level, label = classify_remove_level(
            remove_signal_count=n, momentum_weak_count=mom, priority_score=20
        )
        self.assertEqual(level, REMOVE_LEVEL_STRONG)
        self.assertEqual(label, SEVERITY_LABEL_STRONG)
        hint = rule_precheck(row, {"반도체": "weak"})
        self.assertEqual(hint["remove_level"], REMOVE_LEVEL_STRONG)

    def test_three_signals_two_momentum_not_remove(self):
        """신호 3개 이하 — 모멘텀 2개여도 remove 아님 → caution."""
        row = {
            "sector": "반도체",
            "return_5d": -5,
            "tv_growth_5d_vs_10d": -0.1,
            "drawdown_from_recent_high": 6,
            "position_vs_52w_high": 0.92,
            "sector_relative_strength": 50,
            "data_status": "ok_10d",
        }
        n, flags = count_remove_signals(row, {"반도체": "neutral"})
        self.assertLess(n, REMOVE_MIN_SIGNALS)
        self.assertEqual(momentum_weak_count(flags), 2)
        self.assertFalse(is_remove_eligible(flags, row=row))
        hint = rule_precheck(row, {"반도체": "neutral"})
        self.assertNotEqual(hint["rule_action"], ACTION_REMOVE)
        self.assertEqual(hint["reason_code"], REASON_CAUTION)

    def test_rule_only_judgment_covers_all(self):
        metrics = [
            {
                "ticker": "005930",
                "symbol": "삼성",
                "sector": "반도체",
                "return_5d": 3,
                "tv_growth_5d_vs_10d": 0.1,
                "data_quality": "ok",
            },
            {
                "ticker": "000660",
                "symbol": "SK하이닉스",
                "sector": "반도체",
                "return_5d": -8,
                "tv_growth_5d_vs_10d": -0.2,
                "data_quality": "ok",
            },
        ]
        mood = judge_weekly_sector_mood(metrics)
        j = rule_only_judgment(metrics, mood)
        self.assertEqual(len(j["stocks"]), 2)
        self.assertIn("summary", j)


class TestWeeklyReport(unittest.TestCase):
    def test_slack_text_sections(self):
        judgment = {
            "summary": "주간 요약",
            "keep_count": 1,
            "weaken_count": 2,
            "remove_count": 1,
            "data_check_count": 1,
            "top_keep": ["005930"],
            "stocks": [
                {
                    "ticker": "005930",
                    "symbol": "삼성",
                    "action": "keep",
                    "priority_score": 85,
                    "one_line": "유지 이유",
                    "reasons": ["강세"],
                },
                {
                    "ticker": "000001",
                    "symbol": "약화",
                    "action": "weaken",
                    "priority_score": 55,
                    "one_line": "약화 이유",
                    "metrics": {"return_5d": 0, "sector_relative_strength": 50},
                },
                {
                    "ticker": "000004",
                    "symbol": "주의",
                    "action": "weaken",
                    "reason_code": REASON_CAUTION,
                    "priority_score": 36,
                    "one_line": "주의 이유",
                    "metrics": {"return_5d": -3, "sector_relative_strength": 35},
                },
                {
                    "ticker": "000002",
                    "symbol": "제외",
                    "action": "remove_candidate",
                    "remove_level": REMOVE_LEVEL_REVIEW,
                    "severity_label": SEVERITY_LABEL_REVIEW,
                    "one_line": "제외 이유",
                },
                {
                    "ticker": "000003",
                    "symbol": "한솔케미칼",
                    "action": "data_check_needed",
                    "one_line": "최근 OHLCV 수집 실패",
                },
            ],
        }
        text = build_slack_text(as_of_date="2026-05-21", judgment=judgment)
        self.assertIn("*요약*", text)
        self.assertIn("🟢 핵심 유지", text)
        self.assertIn("🟡 관찰 약화", text)
        self.assertIn("⚠️ 주의 관찰", text)
        self.assertIn("🚫 제외 후보", text)
        self.assertIn("🧪 데이터 확인 필요", text)
        self.assertIn("눌림/돌파 시 우선 확인", text)
        self.assertIn("추격 금지, 거래대금 회복 확인", text)
        self.assertIn("반등 전까지 관심도 낮춤", text)
        self.assertIn("주의 이유", text)
        self.assertIn("최근 OHLCV 수집 실패", text)
        self.assertNotIn("주간 약세", text)

    def test_slack_remove_strong_before_review(self):
        judgment = {
            "summary": "",
            "strong_remove_count": 1,
            "review_remove_count": 1,
            "stocks": [
                {
                    "ticker": "000001",
                    "symbol": "검토종목",
                    "action": "remove_candidate",
                    "remove_level": REMOVE_LEVEL_REVIEW,
                    "severity_label": SEVERITY_LABEL_REVIEW,
                    "priority_score": 24,
                    "one_line": "검토",
                },
                {
                    "ticker": "000002",
                    "symbol": "강한종목",
                    "action": "remove_candidate",
                    "remove_level": REMOVE_LEVEL_STRONG,
                    "severity_label": SEVERITY_LABEL_STRONG,
                    "priority_score": 18,
                    "severity_score": 12,
                    "one_line": "강한",
                },
            ],
        }
        text = build_slack_text(as_of_date="2026-05-21", judgment=judgment)
        self.assertIn(f"*{SEVERITY_LABEL_STRONG}*", text)
        self.assertIn(f"*{SEVERITY_LABEL_REVIEW}*", text)
        self.assertLess(text.index("강한종목"), text.index("검토종목"))
        self.assertLess(
            text.index(f"*{SEVERITY_LABEL_STRONG}*"),
            text.index(f"*{SEVERITY_LABEL_REVIEW}*"),
        )

    def test_slack_remove_tier_caps_independent(self):
        """strong 최대 6·review 최대 2 — 그룹별 cap, review 최소 1개 노출."""
        strong = [
            {
                "ticker": f"{i:06d}",
                "symbol": f"강한{i}",
                "action": "remove_candidate",
                "remove_level": REMOVE_LEVEL_STRONG,
                "severity_score": 10 + i,
                "one_line": f"강{i}",
            }
            for i in range(9)
        ]
        review = [
            {
                "ticker": f"1{i:05d}",
                "symbol": f"검토{i}",
                "action": "remove_candidate",
                "remove_level": REMOVE_LEVEL_REVIEW,
                "severity_score": 20 + i,
                "one_line": f"검{i}",
            }
            for i in range(3)
        ]
        text = build_slack_text(
            as_of_date="2026-05-21",
            judgment={"stocks": strong + review, "summary": ""},
        )
        strong_block = text.split(f"*{SEVERITY_LABEL_REVIEW}*")[0]
        review_block = text.split(f"*{SEVERITY_LABEL_REVIEW}*")[1]
        self.assertEqual(strong_block.count("• 강한"), SLACK_STRONG_REMOVE_MAX)
        self.assertIn("_외 3개_", strong_block)
        self.assertGreaterEqual(review_block.count("• 검토"), 1)
        self.assertLessEqual(review_block.count("• 검토"), SLACK_REVIEW_REMOVE_MAX)
        self.assertIn("• 검토0", review_block)
        self.assertIn("_외 1개_", review_block)

    def test_slack_section_cap_and_overflow(self):
        stocks = [
            {
                "ticker": f"{i:06d}",
                "symbol": f"종목{i}",
                "action": "remove_candidate",
                "remove_level": REMOVE_LEVEL_REVIEW,
                "priority_score": 100 - i,
                "one_line": f"이유{i}",
            }
            for i in range(SLACK_SECTION_MAX + 3)
        ]
        text = build_slack_text(
            as_of_date="2026-05-21",
            judgment={"stocks": stocks, "summary": ""},
        )
        self.assertIn(f"_외 {len(stocks) - SLACK_REVIEW_REMOVE_MAX}개_", text)
        self.assertEqual(text.count("• 종목"), SLACK_REVIEW_REMOVE_MAX)

    def test_slack_caution_from_rule_judgment(self):
        metrics = [
            {
                "ticker": "011200",
                "symbol": "HMM",
                "sector": "해운",
                "return_5d": -1,
                "tv_growth_5d_vs_10d": -0.02,
                "drawdown_from_recent_high": 13,
                "position_vs_52w_high": 0.75,
                "sector_relative_strength": 42,
                "data_status": "ok_10d",
            }
        ]
        j = rule_only_judgment(metrics, {"해운": "neutral"})
        text = build_slack_text(as_of_date="2026-05-21", judgment=j)
        stock = j["stocks"][0]
        if stock.get("reason_code") == REASON_CAUTION:
            self.assertIn("⚠️ 주의 관찰", text)
            self.assertIn("HMM", text)


if __name__ == "__main__":
    unittest.main()
