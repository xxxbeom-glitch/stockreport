"""MVP 3-2~3-4 뉴스 judgment 연결·태깅·Slack QA."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.weekly_watchlist_update.news_context import (
    SLACK_ISSUE_MAX_LEN,
    attach_news_to_judgments,
    clean_display_text,
    collect_issue_tags,
    format_issue_line_rule_based,
    format_slack_issue_line,
    is_direct_news_for_stock,
    load_stock_news,
    normalize_dart_issue_title,
    run_news_llm_summaries,
    select_top_issue,
)


class TestNewsContextQa(unittest.TestCase):
    def test_html_unescape_quot(self):
        self.assertEqual(clean_display_text("삼성 &quot;실적&quot;"), '삼성 "실적"')
        self.assertEqual(clean_display_text("A &amp; B"), "A & B")

    def test_normalize_provisional_earnings(self):
        raw = "연결재무제표기준영업(잠정)실적(공정공시)"
        self.assertEqual(normalize_dart_issue_title(raw), "잠정 실적 발표")

    def test_normalize_supply_contract(self):
        self.assertEqual(
            normalize_dart_issue_title("단일판매ㆍ공급계약체결"),
            "공급계약 체결",
        )
        self.assertEqual(
            normalize_dart_issue_title("[기재정정]단일판매ㆍ공급계약체결"),
            "공급계약 정정",
        )

    def test_normalize_lawsuit_slack_line(self):
        top = select_top_issue(
            [],
            [{"report_nm": "소송등의제기ㆍ신청", "matched_keywords": ["소송"]}],
        )
        line = format_issue_line_rule_based(top)
        self.assertIsNotNone(line)
        assert line is not None
        self.assertIn("리스크 공시", line)
        self.assertIn("소송 제기", line)

    def test_vague_earnings_not_bare_label(self):
        line = format_issue_line_rule_based(
            {
                "kind": "dart",
                "title": "영업",
                "title_normalized": normalize_dart_issue_title("영업"),
                "risk_issue": False,
            }
        )
        self.assertIsNotNone(line)
        assert line is not None
        self.assertNotEqual(line, "공시: 영업")
        self.assertIn("실적", line)

    def test_direct_title_news_beats_description_only(self):
        top = select_top_issue(
            [
                {
                    "title": "시황 브리핑",
                    "description": "테크윙 등 반도체 장비주 강세",
                    "relevance_score": 70,
                    "quality_flags": {
                        "direct_title_match": False,
                        "description_only_match": True,
                    },
                },
                {
                    "title": "테크윙, HBM 테스트 장비 수주",
                    "description": "테크윙이 대형 수주",
                    "relevance_score": 65,
                    "quality_flags": {
                        "direct_title_match": True,
                        "description_only_match": False,
                    },
                },
            ],
            [],
            symbol="테크윙",
        )
        self.assertEqual(top["kind"], "news")
        self.assertTrue(top.get("direct_title_match"))
        self.assertIn("테크윙", top["title"])

    def test_direct_high_score_news_beats_routine_dart(self):
        top = select_top_issue(
            [
                {
                    "title": "동진쎄미켐, 1분기 실적 서프라이즈",
                    "description": "동진쎄미켐 실적 개선",
                    "relevance_score": 60,
                    "quality_flags": {"direct_title_match": True},
                }
            ],
            [
                {
                    "report_nm": "주요사항보고서(자기주식취득결정)",
                    "matched_keywords": ["자기주식"],
                }
            ],
            symbol="동진쎄미켐",
        )
        self.assertEqual(top["kind"], "news")

    def test_risk_dart_beats_strong_news(self):
        top = select_top_issue(
            [
                {
                    "title": "비츠로테크 수주 확대",
                    "description": "비츠로테크",
                    "relevance_score": 80,
                    "quality_flags": {"direct_title_match": True},
                }
            ],
            [{"report_nm": "소송등의제기ㆍ신청", "matched_keywords": ["소송"]}],
            symbol="비츠로테크",
        )
        self.assertEqual(top["kind"], "dart")
        self.assertTrue(top.get("risk_issue"))

    def test_news_slack_prefix(self):
        line = format_issue_line_rule_based(
            {
                "kind": "news",
                "title": "테크윙 HBM 수요 증가",
                "theme_article": False,
            }
        )
        self.assertTrue(line.startswith("뉴스:"))

    def test_korea_circuit_not_jusung_engineering_headline(self):
        title = "코스피 하락에도 굳건…주성엔지니어링 15% 상승"
        news = [
            {
                "title": title,
                "description": "코리아써키트 등 반도체 부품주 동반 상승",
                "relevance_score": 70,
                "quality_flags": {"description_only_match": True},
            }
        ]
        info = is_direct_news_for_stock(
            news[0],
            symbol="코리아써키트",
            peer_names=["주성엔지니어링", "코리아써키트"],
        )
        self.assertFalse(info.direct)
        self.assertTrue(info.possible_indirect_mention)
        top = select_top_issue(news, [], symbol="코리아써키트")
        self.assertIsNone(top)
        self.assertIsNone(format_slack_issue_line({"top_issue": top}))

    def test_sti_not_jusung_engineering_headline(self):
        title = "글로벌 반도체 공정 러시…주성엔지니어링, 대규모 수주 모멘텀 부각"
        news = [
            {
                "title": title,
                "description": "에스티아이 등 장비주 언급",
                "relevance_score": 65,
                "quality_flags": {"description_only_match": True},
            }
        ]
        top = select_top_issue(
            news,
            [],
            symbol="에스티아이",
            ticker="039440",
        )
        self.assertIsNone(top)

    def test_dart_beats_indirect_news(self):
        top = select_top_issue(
            [
                {
                    "title": "주성엔지니어링 수주 쏟아진다",
                    "description": "코리아써키트 포함",
                    "relevance_score": 80,
                }
            ],
            [{"report_nm": "단일판매·공급계약체결", "matched_keywords": ["공급계약"]}],
            symbol="코리아써키트",
        )
        self.assertEqual(top["kind"], "dart")

    def test_description_only_lower_than_direct(self):
        direct = {
            "title": "코리아써키트, 실적 개선 전망",
            "description": "코리아써키트",
            "relevance_score": 50,
        }
        indirect = {
            "title": "주성엔지니어링 급등",
            "description": "코리아써키트 동반",
            "relevance_score": 90,
        }
        top = select_top_issue(
            [indirect, direct],
            [],
            symbol="코리아써키트",
        )
        self.assertEqual(top["kind"], "news")
        self.assertIn("코리아써키트", top["title"])

    def test_slack_unescape_before_truncate(self):
        line = format_slack_issue_line(
            {
                "issue_summary_line": '공시: 삼성 &quot;실적&quot; 호조',
            }
        )
        self.assertIn('"', line or "")
        self.assertNotIn("&quot;", line or "")


class TestNewsContextIntegration(unittest.TestCase):
    def test_load_stock_news_missing(self):
        with patch(
            "agents.weekly_watchlist_update.news_context.stock_news_path",
            return_value=Path("/nonexistent/stock_news_2099-01-01.json"),
        ):
            self.assertIsNone(load_stock_news("2099-01-01"))

    def test_attach_by_ticker_normalized_dart(self):
        judgment = {"stocks": [{"ticker": "089030", "symbol": "테크윙", "sector": "반도체 장비"}]}
        news_data = {
            "stocks": [
                {
                    "ticker": "089030",
                    "symbol": "테크윙",
                    "naver_news": [],
                    "dart_disclosures": [
                        {
                            "report_nm": "단일판매·공급계약체결",
                            "rcept_dt": "20260519",
                            "matched_keywords": ["단일판매"],
                        }
                    ],
                }
            ]
        }
        out = attach_news_to_judgments(judgment, news_data)
        ctx = out["stocks"][0]["news_context"]
        self.assertEqual(ctx["top_issue"]["kind"], "dart")
        self.assertEqual(ctx["top_issue"]["title_normalized"], "공급계약 체결")
        self.assertEqual(ctx["issue_summary_line"], "공시: 공급계약 체결")

    def test_supply_contract_tags(self):
        tags = collect_issue_tags(
            [],
            [{"report_nm": "단일판매·공급계약체결", "matched_keywords": ["공급계약"]}],
        )
        self.assertIn("수주", tags)

    def test_slack_issue_max_length(self):
        long_title = "가" * 80
        line = format_slack_issue_line(
            {"top_issue": {"kind": "news", "title": long_title}, "issue_summary_line": None}
        )
        assert line is not None
        self.assertLessEqual(len(line), SLACK_ISSUE_MAX_LEN)

    def test_no_llm_skips_news_summary(self):
        judgment = {
            "stocks": [
                {
                    "ticker": "005930",
                    "symbol": "삼성전자",
                    "action": "keep",
                    "priority_score": 80,
                    "news_context": {"dart_disclosures": [{"report_nm": "x"}]},
                }
            ]
        }
        with patch(
            "agents.weekly_watchlist_update.news_context.call_primary_json"
        ) as mock_llm:
            out = run_news_llm_summaries(judgment, as_of_date="2026-05-21", use_llm=False)
            mock_llm.assert_not_called()
        self.assertFalse(out.get("news_llm_used"))


if __name__ == "__main__":
    unittest.main()
