"""MVP 4-2 — 신규 후보 에이전트 투표 테스트."""

from __future__ import annotations

import unittest

from agents.weekly_watchlist_update.candidate_agents import (
    apply_vote_to_tier,
    enrich_candidate_with_votes,
    format_agent_check_line,
    run_candidate_agent_votes,
    summarize_votes,
)
from agents.weekly_watchlist_update.candidate_report import (
    build_candidate_slack_text,
    validate_slack_text,
)
from agents.weekly_watchlist_update.candidate_scanner import CandidateScanResult


def _base_row(**overrides) -> dict:
    row = {
        "ticker": "100001",
        "name": "테스트종목",
        "sector_name": "반도체 장비",
        "return_5d_pct": 4.0,
        "tv_increase": True,
        "near_high": True,
        "has_news": True,
        "has_dart": False,
        "current_price": 50000,
        "current_price_fmt": "50,000원",
        "entry_low": 48000,
        "entry_high": 49500,
        "entry_range": "48,000원 ~ 49,500원",
        "distance_pct": 3.0,
        "distance_band": "ok",
        "tier": "yellow",
        "score": 60,
    }
    row.update(overrides)
    return row


def _metrics_from_row(row: dict) -> dict:
    return {
        "return_5d_pct": row.get("return_5d_pct"),
        "tv_increase": row.get("tv_increase"),
        "near_high": row.get("near_high"),
        "latest_trading_value": 2_000_000_000,
    }


class TestVoteTierRules(unittest.TestCase):
    def test_three_approve_zero_reject_is_green(self):
        votes = {
            "price": {"vote": "approve", "reason": "a"},
            "volume": {"vote": "approve", "reason": "b"},
            "news": {"vote": "approve", "reason": "c"},
            "risk": {"vote": "approve", "reason": "d"},
            "sector": {"vote": "hold", "reason": "e"},
        }
        summary = summarize_votes(votes)
        tier, opinion = apply_vote_to_tier(_base_row(), summary, votes)
        self.assertEqual(tier, "green")
        self.assertEqual(opinion, "지금 볼만함")

    def test_two_approve_one_reject_is_yellow(self):
        votes = {
            "price": {"vote": "approve", "reason": "a"},
            "volume": {"vote": "approve", "reason": "b"},
            "news": {"vote": "reject", "reason": "c"},
            "risk": {"vote": "hold", "reason": "d"},
            "sector": {"vote": "hold", "reason": "e"},
        }
        summary = summarize_votes(votes)
        tier, _ = apply_vote_to_tier(_base_row(), summary, votes)
        self.assertEqual(tier, "yellow")

    def test_two_or_more_reject_is_red(self):
        votes = {
            "price": {"vote": "reject", "reason": "a"},
            "volume": {"vote": "reject", "reason": "b"},
            "news": {"vote": "hold", "reason": "c"},
            "risk": {"vote": "hold", "reason": "d"},
            "sector": {"vote": "hold", "reason": "e"},
        }
        summary = summarize_votes(votes)
        tier, _ = apply_vote_to_tier(_base_row(), summary, votes)
        self.assertEqual(tier, "red")

    def test_one_approve_is_red(self):
        votes = {
            "price": {"vote": "approve", "reason": "a"},
            "volume": {"vote": "hold", "reason": "b"},
            "news": {"vote": "hold", "reason": "c"},
            "risk": {"vote": "hold", "reason": "d"},
            "sector": {"vote": "hold", "reason": "e"},
        }
        summary = summarize_votes(votes)
        tier, _ = apply_vote_to_tier(_base_row(), summary, votes)
        self.assertEqual(tier, "red")

    def test_risk_reject_blocks_green(self):
        votes = {
            "price": {"vote": "approve", "reason": "a"},
            "volume": {"vote": "approve", "reason": "b"},
            "news": {"vote": "approve", "reason": "c"},
            "risk": {"vote": "reject", "reason": "d"},
            "sector": {"vote": "approve", "reason": "e"},
        }
        summary = summarize_votes(votes)
        tier, _ = apply_vote_to_tier(_base_row(), summary, votes)
        self.assertNotEqual(tier, "green")
        self.assertEqual(tier, "yellow")


class TestCheckLine(unittest.TestCase):
    def test_format_icons(self):
        votes = {
            "price": {"vote": "approve", "reason": ""},
            "volume": {"vote": "hold", "reason": ""},
            "news": {"vote": "hold", "reason": ""},
            "risk": {"vote": "approve", "reason": ""},
        }
        line = format_agent_check_line(votes)
        self.assertIn("체크:", line)
        self.assertIn("가격 ✅", line)
        self.assertIn("거래 △", line)
        self.assertIn("뉴스 △", line)
        self.assertIn("위험 괜찮음", line)

    def test_risk_reject_shows_warning(self):
        votes = {
            "price": {"vote": "hold", "reason": ""},
            "volume": {"vote": "hold", "reason": ""},
            "news": {"vote": "hold", "reason": ""},
            "risk": {"vote": "reject", "reason": ""},
        }
        line = format_agent_check_line(votes)
        self.assertIn("위험 ⚠️", line)


class TestEnrichAndSlack(unittest.TestCase):
    def _enriched(self, **row_kw) -> dict:
        row = _base_row(**row_kw)
        return enrich_candidate_with_votes(row, _metrics_from_row(row))

    def test_slack_has_check_line(self):
        row = self._enriched()
        row["tier"] = "green"
        scan = CandidateScanResult(as_of_date="2026-05-21")
        scan.slack_green = [row]
        text = build_candidate_slack_text(scan)
        self.assertIn("체크:", text)
        self.assertIn("가격", text)
        self.assertEqual(validate_slack_text(text), [])

    def test_slack_no_forbidden_words(self):
        row = self._enriched(return_5d_pct=5, tv_increase=True, near_high=True)
        row["tier"] = "green"
        scan = CandidateScanResult(as_of_date="2026-05-21")
        scan.slack_green = [row]
        text = build_candidate_slack_text(scan)
        self.assertNotIn("추천", text)
        self.assertNotIn("진입", text)
        if "매수" in text:
            self.assertIn("외국인 매수", text)

    def test_agent_votes_structure(self):
        row = _base_row()
        votes = run_candidate_agent_votes(row, _metrics_from_row(row))
        self.assertIn("price", votes)
        self.assertIn("volume", votes)
        self.assertEqual(set(votes["price"].keys()), {"vote", "reason"})


if __name__ == "__main__":
    unittest.main()
