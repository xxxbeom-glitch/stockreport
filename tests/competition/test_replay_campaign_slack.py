"""REPLAY campaign, Slack policy, Firebase isolation tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.trading.competition.replay.calendar import resolve_replay_dates
from src.trading.competition.replay.runner import run_replay_smoke
from src.trading.competition.replay.slack_reports import (
    send_fatal_replay_error,
    send_monthly_report_link,
    send_weekly_report_link,
)


class ReplaySlackPolicyTests(unittest.TestCase):
    def test_smoke_does_not_call_slack_summary(self) -> None:
        with patch("src.trading.competition.replay.runner.run_replay_single_day") as mock_day:
            mock_day.return_value = {"ok": True, "replay_run_id": "r1"}
            run_replay_smoke("20241218", send_slack=True)
            self.assertTrue(mock_day.called)

    def test_weekly_link_message_format(self) -> None:
        with patch("src.trading.competition.replay.slack_reports._post_slack") as mock_post:
            mock_post.return_value = {"ok": True}
            send_weekly_report_link(
                {"week_key": "w51", "label": "12월 3주차", "url": "http://x/?mode=replay&report=w51"},
                campaign_id="camp1",
            )
            payload = mock_post.call_args[0][0]
            self.assertIn("주간 리포트", payload["text"])
            self.assertNotIn("1일 검증 완료", payload["text"])

    def test_monthly_link_message_format(self) -> None:
        with patch("src.trading.competition.replay.slack_reports._post_slack") as mock_post:
            mock_post.return_value = {"ok": True}
            send_monthly_report_link(
                {"month_key": "m202412", "label": "2024년 12월"},
                campaign_id="camp1",
            )
            self.assertIn("월간", mock_post.call_args[0][0]["text"])

    def test_fatal_error_allowed(self) -> None:
        with patch("src.trading.competition.replay.slack_reports._post_slack") as mock_post:
            mock_post.return_value = {"ok": True, "dry_run": True}
            r = send_fatal_replay_error("storage failed", dry_run=True)
            self.assertTrue(r.get("ok"))


class ReplayCalendarTests(unittest.TestCase):
    def test_smoke_single_date(self) -> None:
        self.assertEqual(resolve_replay_dates("smoke_1day", "20241218"), ["20241218"])

    def test_full_audit_uses_fixed_period(self) -> None:
        with patch("src.trading.competition.replay.calendar.list_trading_dates") as mock_list:
            mock_list.return_value = ["20260102", "20260103"]
            from src.trading.competition.replay.period import FULL_AUDIT_END, FULL_AUDIT_START

            dates = resolve_replay_dates("full_audit", "20241218", "20241220")
        mock_list.assert_called_once_with(FULL_AUDIT_START, FULL_AUDIT_END)
        self.assertEqual(dates, ["20260102", "20260103"])


class ReplayFirestoreIsolationTests(unittest.TestCase):
    def test_collection_names_distinct_from_live(self) -> None:
        from src.trading.competition.constants import (
            COLLECTION_ACCOUNTS,
            COLLECTION_REPLAY_RUNS,
        )

        self.assertNotEqual(COLLECTION_REPLAY_RUNS, COLLECTION_ACCOUNTS)
        self.assertTrue(COLLECTION_REPLAY_RUNS.startswith("competition_replay"))


if __name__ == "__main__":
    unittest.main()
