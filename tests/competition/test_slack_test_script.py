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

    def test_payload_uses_top_level_text_for_slack(self) -> None:
        payload = slack_test.build_slack_test_payload()
        self.assertEqual(payload["text"], slack_test.TEST_MESSAGE)
        self.assertIn("blocks", payload)
        self.assertEqual(payload["blocks"][0]["text"]["text"], slack_test.TEST_MESSAGE)

    def test_fails_without_webhook(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ("COMPETITION_SLACK_WEBHOOK", "SLACK_WEBHOOK_URL")}
        with patch.dict(os.environ, env, clear=True):
            code = slack_test.main()
        self.assertEqual(code, 1)

    def test_rejects_workflow_trigger_url(self) -> None:
        url = "https://hooks.slack.com/triggers/T123/456/789"
        result = slack_test.send_slack_test(url)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "workflow_trigger_webhook")

    @patch("urllib.request.urlopen")
    def test_sends_text_and_blocks_via_incoming_webhook(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        url = "https://hooks.slack.com/services/T/B/x"
        result = slack_test.send_slack_test(url)
        self.assertTrue(result["ok"])
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["text"], slack_test.TEST_MESSAGE)
        self.assertEqual(payload["blocks"][0]["type"], "section")

    @patch("urllib.request.urlopen")
    def test_fails_when_response_body_not_ok(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"invalid_payload"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = slack_test.send_slack_test("https://hooks.slack.com/services/T/B/x")
        self.assertFalse(result["ok"])
        self.assertEqual(result["response_body"], "invalid_payload")


if __name__ == "__main__":
    unittest.main()
