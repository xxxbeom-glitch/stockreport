# -*- coding: utf-8 -*-
"""Tests for Slack webhook test script (no network)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.test_competition_slack as slack_test


class SlackTestScriptTest(unittest.TestCase):
    def test_message_contains_expected_lines(self) -> None:
        self.assertIn("[AI 투자 경쟁앱] Slack 연결 테스트 완료", slack_test.TEST_MESSAGE)
        self.assertIn("계좌 데이터 변경은 없습니다", slack_test.TEST_MESSAGE)

    def test_fails_without_webhook(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ("COMPETITION_SLACK_WEBHOOK", "SLACK_WEBHOOK_URL")}
        with patch.dict(os.environ, env, clear=True):
            code = slack_test.main()
        self.assertEqual(code, 1)

    @patch("urllib.request.urlopen")
    def test_sends_exact_message_via_webhook(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"COMPETITION_SLACK_WEBHOOK": "https://hooks.slack.com/services/T/B/x"}, clear=False):
            code = slack_test.main()
        self.assertEqual(code, 0)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["text"], slack_test.TEST_MESSAGE)


if __name__ == "__main__":
    unittest.main()
