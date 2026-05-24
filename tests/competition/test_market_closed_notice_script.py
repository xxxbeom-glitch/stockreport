# -*- coding: utf-8 -*-
"""Tests for market-closed Slack notice script (no network)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.test_competition_market_closed_notice as notice

KST = ZoneInfo("Asia/Seoul")


class MarketClosedNoticeScriptTest(unittest.TestCase):
    def test_message_contains_expected_lines(self) -> None:
        self.assertIn("[AI 투자 경쟁앱] 현재 휴장일 또는 거래시간 외입니다", notice.MARKET_CLOSED_MESSAGE)
        self.assertIn("매수·매도 판단 및 체결을 실행하지 않습니다", notice.MARKET_CLOSED_MESSAGE)

    def test_weekend_detected_as_closed(self) -> None:
        # 2026-05-24 is Sunday
        sunday = datetime(2026, 5, 24, 12, 0, tzinfo=KST)
        closed, reason = notice.market_closed_reason(sunday)
        self.assertTrue(closed)
        self.assertEqual(reason, "weekend_closed")

    def test_regular_session_not_closed(self) -> None:
        tuesday_open = datetime(2026, 5, 26, 10, 0, tzinfo=KST)
        closed, reason = notice.market_closed_reason(tuesday_open)
        self.assertFalse(closed)
        self.assertEqual(reason, "regular")

    def test_holiday_detected_as_closed(self) -> None:
        childrens_day = datetime(2026, 5, 5, 10, 0, tzinfo=KST)
        closed, reason = notice.market_closed_reason(childrens_day)
        self.assertTrue(closed)
        self.assertEqual(reason, "holiday")

    def test_payload_uses_top_level_text_for_slack(self) -> None:
        payload = notice.build_market_closed_payload()
        self.assertEqual(payload["text"], notice.MARKET_CLOSED_MESSAGE)
        self.assertEqual(payload["blocks"][0]["text"]["text"], notice.MARKET_CLOSED_MESSAGE)

    @patch("scripts.test_competition_market_closed_notice.market_closed_reason", return_value=(False, "regular"))
    def test_main_skips_send_when_market_open(self, _mock_reason: MagicMock) -> None:
        code = notice.main()
        self.assertEqual(code, 0)

    @patch("scripts.test_competition_market_closed_notice.market_closed_reason", return_value=(True, "weekend_closed"))
    def test_main_fails_without_webhook_when_closed(self, _mock_reason: MagicMock) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ("COMPETITION_SLACK_WEBHOOK", "SLACK_WEBHOOK_URL")}
        with patch.dict(os.environ, env, clear=True):
            code = notice.main()
        self.assertEqual(code, 1)

    @patch("urllib.request.urlopen")
    @patch(
        "scripts.test_competition_market_closed_notice.market_closed_reason",
        return_value=(True, "weekend_closed"),
    )
    def test_main_sends_when_closed(self, _mock_reason: MagicMock, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch.dict(
            os.environ,
            {"COMPETITION_SLACK_WEBHOOK": "https://hooks.slack.com/services/T/B/x"},
            clear=False,
        ):
            code = notice.main()
        self.assertEqual(code, 0)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["text"], notice.MARKET_CLOSED_MESSAGE)


if __name__ == "__main__":
    unittest.main()
