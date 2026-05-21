"""MVP 3-1 / 3-1.5 뉴스/공시 수집 레이어."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agents.weekly_watchlist_update.news_collect import (
    MAX_QUERIES_PER_STOCK,
    analyze_match,
    build_quality_flags,
    collect_naver_news_for_stock,
    extract_news_domain,
    filter_and_rank_news,
    is_homonym_noise,
    news_relevance_score,
    normalize_title,
    search_queries_for_symbol,
    sector_keyword,
    select_top_with_domain_cap,
    strip_html,
)
from agents.weekly_watchlist_update.stock_news import (
    collect_stock_news_payload,
    write_stock_news_file,
)
from data import api_env, dart_client, naver_news_client

KST = timezone(timedelta(hours=9))


def _item(
    title: str,
    description: str = "",
    *,
    link: str = "",
    pub: str = "Thu, 21 May 2026 09:00:00 +0900",
) -> dict:
    return {
        "title": title,
        "description": description or title,
        "pubDate": pub,
        "link": link or f"https://news.example/{hash(title) % 10000}",
        "originallink": "",
    }


class TestNewsCollectHelpers(unittest.TestCase):
    def test_strip_html(self):
        self.assertEqual(strip_html("<b>삼성</b>전자"), "삼성전자")

    def test_normalize_title_dedupe(self):
        a = normalize_title("삼성 전자 — 실적")
        b = normalize_title("삼성전자 실적")
        self.assertEqual(a, b)

    def test_sector_keyword(self):
        self.assertEqual(sector_keyword("반도체 소재"), "반도체")
        self.assertEqual(sector_keyword("방산·우주"), "방산")

    def test_search_queries_taekwang_aliases(self):
        queries = search_queries_for_symbol("태광", "조선기자재", ticker="023160")
        self.assertIn("태광 조선기자재", queries)
        self.assertNotIn("태광그룹", queries)
        self.assertLessEqual(len(queries), MAX_QUERIES_PER_STOCK)

    def test_theme_title_penalty(self):
        now = datetime(2026, 5, 21, tzinfo=KST)
        direct = _item("삼성전자 실적", "삼성전자")
        theme = _item("반도체주 강세", "삼성전자 등 상승")
        s_direct = news_relevance_score(direct, symbol="삼성전자", sector_kw="", now=now)
        s_theme = news_relevance_score(theme, symbol="삼성전자", sector_kw="", now=now)
        self.assertGreater(s_direct, s_theme)

    def test_homonym_noise_taekwang_group(self):
        self.assertTrue(
            is_homonym_noise("태광", "태광그룹 실적 개선", "태광그룹이 호실적을 기록했다")
        )
        self.assertFalse(
            is_homonym_noise(
                "태광",
                "태광 조선기자재 수주",
                "태광 피팅 사업 확대",
            )
        )

    def test_direct_title_scores_higher_than_description_only(self):
        now = datetime(2026, 5, 21, 12, 0, tzinfo=KST)
        direct = _item("삼성전자 실적 서프라이즈", "반도체 호조")
        mention = _item("코스피 장 마감", "외국인 매수에 삼성전자 포함")
        s_direct = news_relevance_score(
            direct, symbol="삼성전자", sector_kw="", now=now
        )
        s_mention = news_relevance_score(
            mention, symbol="삼성전자", sector_kw="", now=now
        )
        self.assertGreater(s_direct, s_mention)

    def test_exclude_news_without_symbol(self):
        now = datetime(2026, 5, 21, tzinfo=KST)
        items = [_item("코스피 상승 마감", "시장 전반 강세")]
        out = filter_and_rank_news(
            items, symbol="삼성전자", sector_kw="반도체", now=now
        )
        self.assertEqual(out, [])

    def test_taekwang_group_not_in_top(self):
        now = datetime(2026, 5, 21, tzinfo=KST)
        items = [
            _item(
                "태광그룹, 1분기 영업이익 급증",
                "태광그룹이 실적을 발표했다",
                link="https://a.example/g1",
            ),
            _item(
                "태광, 조선기자재 수주 확대",
                "태광이 대형 수주를 따냈다",
                link="https://b.example/good",
            ),
            _item(
                "반도체주 강세, 소부장주 동반 상승",
                "태광 등 조선기자재 종목도 언급",
                link="https://c.example/theme",
            ),
        ]
        out = filter_and_rank_news(items, symbol="태광", sector_kw="조선", now=now)
        titles = [x["title"] for x in out]
        self.assertNotIn("태광그룹, 1분기 영업이익 급증", titles)
        self.assertTrue(any("태광" in t and "그룹" not in t for t in titles))

    def test_title_direct_match_ranks_above_description_mention(self):
        now = datetime(2026, 5, 21, tzinfo=KST)
        items = [
            _item(
                "시황 브리핑",
                "하나머티리얼즈, 동진쎄미켐, 솔브레인 등 반도체 소재주 강세",
                link="https://d1.example/a",
            ),
            _item(
                "동진쎄미켐, 1분기 실적 호조",
                "영업이익이 시장 기대를 상회",
                link="https://d2.example/b",
            ),
        ]
        out = filter_and_rank_news(
            items, symbol="동진쎄미켐", sector_kw="반도체", now=now
        )
        self.assertGreaterEqual(len(out), 1)
        self.assertIn("동진쎄미켐", out[0]["title"])
        self.assertTrue(out[0]["quality_flags"]["direct_title_match"])

    def test_domain_cap_max_two_per_domain(self):
        now = datetime(2026, 5, 21, tzinfo=KST)
        domain_a = "pinpointnews.co.kr"
        domain_b = "othernews.co.kr"
        items = []
        for i in range(3):
            items.append(
                {
                    **_item(
                        f"삼성전자 뉴스 A{i}",
                        "삼성전자 실적",
                        link=f"https://{domain_a}/n{i}",
                    ),
                    "originallink": f"https://{domain_a}/n{i}",
                }
            )
        items.append(
            {
                **_item(
                    "삼성전자 뉴스 B",
                    "삼성전자 실적",
                    link=f"https://{domain_b}/n0",
                ),
                "originallink": f"https://{domain_b}/n0",
            }
        )
        out = filter_and_rank_news(
            items, symbol="삼성전자", sector_kw="", now=now, top_n=3
        )
        domains = [extract_news_domain(x) for x in out]
        self.assertEqual(len(out), 3)
        self.assertLessEqual(domains.count(domain_a), 2)
        self.assertGreaterEqual(domains.count(domain_b), 1)

    def test_select_top_with_domain_cap_unit(self):
        candidates = [
            {"relevance_score": 90, "domain": "a.com", "pubDate": "1"},
            {"relevance_score": 80, "domain": "a.com", "pubDate": "2"},
            {"relevance_score": 70, "domain": "a.com", "pubDate": "3"},
            {"relevance_score": 60, "domain": "b.com", "pubDate": "4"},
        ]
        for c in candidates:
            c["quality_flags"] = build_quality_flags(
                analyze_match({"title": "삼성전자", "description": ""}, symbol="삼성전자")
            )
        out = select_top_with_domain_cap(candidates, top_n=3, max_per_domain=2)
        self.assertEqual(len(out), 3)
        self.assertEqual(sum(1 for x in out if x["domain"] == "a.com"), 2)

    def test_dedupe_by_url(self):
        now = datetime(2026, 5, 21, tzinfo=KST)
        items = [
            _item("삼성전자 실적", "삼성전자", link="https://news.example/1"),
            _item("삼성전자 실적(중복)", "삼성전자", link="https://news.example/1"),
        ]
        out = filter_and_rank_news(
            items, symbol="삼성전자", sector_kw="", now=now, top_n=5
        )
        self.assertEqual(len(out), 1)

    def test_exclude_news_older_than_30_days(self):
        now = datetime(2026, 5, 21, tzinfo=KST)
        old = (now - timedelta(days=40)).strftime("%a, %d %b %Y %H:%M:%S +0900")
        items = [_item("삼성전자 공시", "삼성전자", pub=old)]
        out = filter_and_rank_news(items, symbol="삼성전자", sector_kw="", now=now)
        self.assertEqual(out, [])

    def test_quality_flags_on_output(self):
        now = datetime(2026, 5, 21, tzinfo=KST)
        items = [_item("삼성전자 실적 발표", "삼성전자 영업이익 증가")]
        out = filter_and_rank_news(items, symbol="삼성전자", sector_kw="", now=now)
        flags = out[0]["quality_flags"]
        self.assertTrue(flags["direct_title_match"])
        self.assertFalse(flags["possible_name_noise"])


class TestDartFilter(unittest.TestCase):
    def test_is_important_disclosure(self):
        self.assertTrue(dart_client.is_important_disclosure("단일판매·공급계약체결"))
        self.assertFalse(dart_client.is_important_disclosure("주주총소집공고"))

    def test_fetch_important_top3(self):
        with patch("data.dart_client.fetch_disclosure_items") as mock_fetch:
            mock_fetch.return_value = [
                {"report_nm": "정기공시", "rcept_dt": "20260520"},
                {"report_nm": "단일판매·공급계약", "rcept_dt": "20260521"},
                {"report_nm": "잠정실적공시", "rcept_dt": "20260519"},
                {"report_nm": "기타", "rcept_dt": "20260518"},
            ]
            out = dart_client.fetch_important_disclosure_items("005930", top_n=3)
        self.assertEqual(len(out), 2)
        self.assertIn("단일판매", out[0]["report_nm"])


class TestStockNewsIntegration(unittest.TestCase):
    def setUp(self) -> None:
        api_env._DOTENV_DONE = True
        naver_news_client._WARNED_NO_CREDENTIALS = False
        dart_client._WARNED_NO_KEY = False
        dart_client._STOCK_TO_CORP = None

    def test_skip_when_no_api_keys(self):
        with patch.dict("os.environ", {}, clear=True):
            payload = collect_stock_news_payload(
                as_of_date="2026-05-21",
                metrics=[
                    {
                        "ticker": "005930",
                        "symbol": "삼성전자",
                        "sector": "반도체",
                    }
                ],
            )
        self.assertTrue(payload["sources"]["naver_news"]["skipped"])
        self.assertTrue(payload["sources"]["dart_disclosures"]["skipped"])
        self.assertEqual(payload["version"], "weekly_watchlist_news_v2")
        stock = payload["stocks"][0]
        self.assertEqual(stock["news_count"], 0)
        self.assertEqual(stock["dart_count"], 0)

    @patch("agents.weekly_watchlist_update.stock_news.fetch_important_disclosure_items")
    @patch("agents.weekly_watchlist_update.stock_news.collect_naver_news_for_stock")
    @patch("agents.weekly_watchlist_update.stock_news.is_dart_configured", return_value=True)
    @patch(
        "agents.weekly_watchlist_update.stock_news.is_naver_news_configured",
        return_value=True,
    )
    def test_json_structure(
        self,
        _naver_cfg: unittest.mock.MagicMock,
        _dart_cfg: unittest.mock.MagicMock,
        mock_naver: unittest.mock.MagicMock,
        mock_dart: unittest.mock.MagicMock,
    ) -> None:
        mock_naver.return_value = [
            {
                "title": "삼성전자 실적",
                "description": "요약",
                "pubDate": "Thu, 21 May 2026 09:00:00 +0900",
                "link": "https://n.example/1",
                "originallink": "https://o.example/1",
                "relevance_score": 50,
                "quality_flags": {
                    "direct_title_match": True,
                    "description_only_match": False,
                    "theme_article": False,
                    "possible_name_noise": False,
                    "domain_limited": False,
                },
                "query": "삼성전자",
                "source": "naver_search_news",
            }
        ]
        mock_dart.return_value = [
            {
                "report_nm": "단일판매·공급계약",
                "rcept_dt": "20260521",
                "matched_keywords": ["단일판매"],
                "source": "opendart",
            }
        ]
        payload = collect_stock_news_payload(
            as_of_date="2026-05-21",
            metrics=[{"ticker": "005930", "symbol": "삼성전자", "sector": "반도체"}],
        )
        stock = payload["stocks"][0]
        self.assertEqual(stock["news_count"], 1)
        self.assertEqual(stock["dart_count"], 1)
        self.assertIn("quality_flags", stock["naver_news"][0])
        self.assertIn("params", payload)

    @patch("agents.weekly_watchlist_update.news_collect.search_raw_news")
    def test_collect_naver_uses_alias_queries(
        self, mock_search: unittest.mock.MagicMock
    ) -> None:
        mock_search.return_value = [
            {
                "title": "HD현대미포 수주",
                "description": "HD현대미포",
                "pubDate": "Thu, 21 May 2026 09:00:00 +0900",
                "link": "https://a/1",
                "originallink": "",
            }
        ]
        collect_naver_news_for_stock("HD현대미포", "조선")
        queries = [c.args[0] for c in mock_search.call_args_list]
        self.assertIn("현대미포조선", queries)

    def test_write_stock_news_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            with patch(
                "agents.weekly_watchlist_update.stock_news.NEWS_DIR",
                out_dir,
            ):
                path = write_stock_news_file(
                    {
                        "version": "weekly_watchlist_news_v2",
                        "as_of_date": "2026-05-21",
                        "stocks": [],
                    },
                    as_of_date="2026-05-21",
                )
            self.assertEqual(path.name, "stock_news_2026-05-21.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], "weekly_watchlist_news_v2")


if __name__ == "__main__":
    unittest.main()
