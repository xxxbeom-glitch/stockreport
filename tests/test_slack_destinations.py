"""Slack 목적별 채널 해석."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from utils import slack_destinations as sd


class SlackDestinationsTests(unittest.TestCase):
    def test_buy_candidate_prefers_webhook(self) -> None:
        env = {
            "SLACK_BUY_CANDIDATE_WEBHOOK": "https://hooks.slack.com/services/T/B/x",
            "SLACK_BUY_CANDIDATE_CHANNEL": "C111",
            "SLACK_CHANNEL_KR": "C999",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(
                sd.resolve_buy_candidate_destination(),
                "https://hooks.slack.com/services/T/B/x",
            )

    def test_watchlist_report_channel_only(self) -> None:
        env = {
            "SLACK_WATCHLIST_REPORT_CHANNEL": "C222",
            "SLACK_BUY_CANDIDATE_CHANNEL": "C111",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(sd.resolve_watchlist_report_destination(), "C222")

    def test_is_incoming_webhook(self) -> None:
        self.assertTrue(sd.is_incoming_webhook("https://hooks.slack.com/foo"))
        self.assertFalse(sd.is_incoming_webhook("C01234567"))


if __name__ == "__main__":
    unittest.main()
