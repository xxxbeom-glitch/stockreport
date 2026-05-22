"""AI 모델 정책 — 구버전 fallback 금지."""

from __future__ import annotations

import os
import unittest

from agents.ai import model_config
from agents.kr_intraday_slack.llm_client import primary_config, social_config, summary_config


class TestModelConfig(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_defaults_are_policy_models(self) -> None:
        os.environ.pop("AI_MODEL", None)
        os.environ.pop("AI_SUMMARY_MODEL", None)
        os.environ.pop("AI_SOCIAL_MODEL", None)
        self.assertEqual(model_config.GEMINI_MODEL_ID, "gemini-3.1-pro-preview")
        self.assertEqual(model_config.DEEPSEEK_MODEL_ID, "deepseek-v4-pro")
        self.assertEqual(model_config.GROK_MODEL_ID, "grok-4.3")

    def test_llm_client_no_legacy_fallback(self) -> None:
        os.environ.pop("AI_MODEL", None)
        os.environ.pop("DEEPSEEK_MODEL", None)
        self.assertEqual(primary_config()["model"], "deepseek-v4-pro")
        self.assertNotIn(primary_config()["model"], model_config.FORBIDDEN_MODEL_IDS)
        os.environ.pop("AI_SOCIAL_MODEL", None)
        os.environ.pop("GROK_MODEL", None)
        self.assertEqual(social_config()["model"], "grok-4.3")
        os.environ.pop("AI_SUMMARY_MODEL", None)
        os.environ.pop("GEMINI_SUMMARY_MODEL", None)
        self.assertEqual(summary_config()["model"], "gemini-3.1-pro-preview")


if __name__ == "__main__":
    unittest.main()
