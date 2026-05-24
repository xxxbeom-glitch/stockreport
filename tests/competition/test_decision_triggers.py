# -*- coding: utf-8
"""Phase 4 decision trigger tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.decision.models import TRIGGER_TYPES
from src.trading.competition.decision.strategy_scouts import (
    scout_team_a,
    scout_team_c,
    scout_team_d,
)
from src.trading.competition.decision.triggers import (
    build_actionable_event_triggers,
    build_all_decision_triggers,
    build_position_triggers,
    build_strategy_triggers,
)
from src.trading.competition.models import Position, TeamAccount, TeamPositions


SAMPLE_UNIVERSE = [
    {
        "ticker": "005930",
        "name": "삼성전자",
        "avg_trading_value_20d_krw": 800_000_000_000,
        "current_trading_value_krw": 1_600_000_000_000,
        "change_rate_pct": 4.5,
        "current_price_krw": 70000,
    },
    {
        "ticker": "000660",
        "name": "SK하이닉스",
        "avg_trading_value_20d_krw": 600_000_000_000,
        "current_trading_value_krw": 700_000_000_000,
        "change_rate_pct": -5.0,
        "current_price_krw": 180000,
    },
    {
        "ticker": "035420",
        "name": "NAVER",
        "avg_trading_value_20d_krw": 2_000_000_000,
        "change_rate_pct": 0.5,
    },
]


class StrategyScoutTest(unittest.TestCase):
    def test_team_a_picks_breakout(self) -> None:
        cands = scout_team_a(SAMPLE_UNIVERSE)
        self.assertTrue(cands)
        self.assertEqual(cands[0].ticker, "005930")

    def test_team_d_picks_pullback(self) -> None:
        cands = scout_team_d(SAMPLE_UNIVERSE)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].ticker, "000660")

    def test_team_c_respects_liquidity(self) -> None:
        cands = scout_team_c(SAMPLE_UNIVERSE, foreign_net_fetcher=lambda _: 1000.0)
        tickers = {c.ticker for c in cands}
        self.assertIn("005930", tickers)
        self.assertNotIn("035420", tickers)


class DecisionTriggerTest(unittest.TestCase):
    def test_trigger_types_constant(self) -> None:
        self.assertEqual(
            list(TRIGGER_TYPES),
            [
                "STRATEGY_CANDIDATE_REVIEW",
                "ACTIONABLE_EVENT_REVIEW",
                "POSITION_REVIEW",
            ],
        )

    @patch("src.trading.competition.decision.triggers.load_eligible_universe")
    @patch("src.trading.competition.decision.strategy_scouts.enrich_universe_change_rates")
    def test_strategy_trigger_per_team(
        self, _enrich, mock_universe
    ) -> None:
        mock_universe.return_value = SAMPLE_UNIVERSE
        triggers = build_strategy_triggers("sess1", enrich_market=False)
        self.assertEqual(len(triggers), 4)
        self.assertTrue(all(t.trigger_type == "STRATEGY_CANDIDATE_REVIEW" for t in triggers))
        team_a = next(t for t in triggers if t.team_id == "A")
        self.assertGreater(len(team_a.candidates), 0)

    def test_actionable_event_triggers_per_team(self) -> None:
        events = [
            {
                "event_id": "e1",
                "event_type": "NEWS_MATERIAL",
                "importance": "HIGH",
                "summary": "실적 서프라이즈",
                "direct_tickers": ["005930"],
                "affected_teams": ["A", "B"],
                "evidence_ids": ["news:1"],
                "requires_position_review": False,
            }
        ]
        triggers = build_actionable_event_triggers("sess1", events=events)
        self.assertEqual(len(triggers), 2)
        self.assertTrue(all(t.trigger_type == "ACTIONABLE_EVENT_REVIEW" for t in triggers))

    @patch("src.trading.competition.decision.triggers.load_all_accounts")
    @patch("src.trading.competition.decision.triggers.load_all_positions")
    def test_position_review_on_session(self, mock_pos, mock_acc) -> None:
        mock_acc.return_value = {
            "A": TeamAccount(team_id="A", cash_krw=100_000, total_assets_krw=400_000),
        }
        mock_pos.return_value = {
            "A": TeamPositions(
                team_id="A",
                positions=[
                    Position(
                        ticker="005930",
                        name="삼성전자",
                        quantity=2,
                        avg_price_krw=65000,
                        current_price_krw=70000,
                    )
                ],
            ),
        }
        triggers = build_position_triggers("sess1", session_transition=True)
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].trigger_type, "POSITION_REVIEW")
        self.assertEqual(len(triggers[0].positions), 1)

    @patch("src.trading.competition.decision.triggers.load_actionable_events")
    @patch("src.trading.competition.decision.triggers.load_all_accounts")
    @patch("src.trading.competition.decision.triggers.load_all_positions")
    @patch("src.trading.competition.decision.triggers.load_eligible_universe")
    @patch("src.trading.competition.decision.strategy_scouts.enrich_universe_change_rates")
    def test_build_all_three_types(
        self, _enrich, mock_universe, mock_pos, mock_acc, mock_events
    ) -> None:
        mock_universe.return_value = SAMPLE_UNIVERSE
        mock_acc.return_value = {}
        mock_pos.return_value = {
            "B": TeamPositions(
                team_id="B",
                positions=[
                    Position(
                        ticker="000660",
                        name="SK하이닉스",
                        quantity=1,
                        avg_price_krw=170000,
                    )
                ],
            ),
        }
        mock_events.return_value = [
            {
                "event_id": "e1",
                "event_type": "DISCLOSURE_MATERIAL",
                "importance": "CRITICAL",
                "summary": "공시",
                "direct_tickers": ["005930"],
                "affected_teams": ["B"],
                "holding_teams": ["B"],
                "evidence_ids": ["dart:1"],
                "requires_position_review": True,
            }
        ]
        triggers = build_all_decision_triggers("sess_full", enrich_market=False)
        types = {t.trigger_type for t in triggers}
        self.assertIn("STRATEGY_CANDIDATE_REVIEW", types)
        self.assertIn("ACTIONABLE_EVENT_REVIEW", types)
        self.assertIn("POSITION_REVIEW", types)


if __name__ == "__main__":
    unittest.main()
