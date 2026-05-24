# -*- coding: utf-8 -*-
"""Static checks for competition_auto_ops workflow dispatch safety."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "competition_auto_ops.yml"


class WorkflowSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def _block(self, step_name: str) -> str:
        pattern = rf"- name: {re.escape(step_name)}.*?(\n      - name: |\Z)"
        match = re.search(pattern, self.text, re.DOTALL)
        self.assertIsNotNone(match, f"step not found: {step_name}")
        return match.group(0)  # type: ignore[union-attr]

    def test_workflow_file_exists(self) -> None:
        self.assertTrue(WORKFLOW.is_file())

    def test_slack_webhook_mapping_uses_trading_secret(self) -> None:
        self.assertIn(
            "COMPETITION_SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK_TRADING }}",
            self.text,
        )

    def test_no_mock_llm_or_local_mirror_env_set(self) -> None:
        self.assertIsNone(
            re.search(r"^\s*COMPETITION_USE_MOCK_LLM:", self.text, re.MULTILINE),
            "COMPETITION_USE_MOCK_LLM must not be set in workflow env",
        )
        self.assertIsNone(
            re.search(r"^\s*COMPETITION_ALLOW_LOCAL_MIRROR:", self.text, re.MULTILINE),
            "COMPETITION_ALLOW_LOCAL_MIRROR must not be set in workflow env",
        )

    def test_session_live_step_has_no_dry_run_flag(self) -> None:
        session_block = self._block("Run competition session (live)")
        self.assertNotIn("--dry-run", session_block)
        self.assertIn("--live-llm", session_block)
        self.assertIn('COMPETITION_SLACK_DRY_RUN: "0"', session_block)

    def test_session_step_gated_on_schedule_or_manual_live(self) -> None:
        session_block = self._block("Run competition session (live)")
        self.assertRegex(session_block, r"github\.event_name == 'schedule'")
        self.assertRegex(
            session_block,
            r"inputs\.dry_run == false && inputs\.live_llm == true",
        )

    def test_weekly_report_friday_schedule_only(self) -> None:
        weekly_block = self._block("Weekly report (Friday 20:00 KST schedule only)")
        self.assertRegex(weekly_block, r"github\.event_name == 'schedule'")
        self.assertRegex(weekly_block, r"github\.event\.schedule == '0 11 \* \* 5'")
        self.assertNotIn("workflow_dispatch", weekly_block)

    def test_manual_dry_run_uses_no_persist_triggers(self) -> None:
        block = self._block("Build decision triggers (manual dry-run, no persist)")
        self.assertIn("--dry-run", block)
        self.assertIn("inputs.dry_run == true", block)

    def test_manual_dry_run_skips_live_trigger_persist(self) -> None:
        live_block = self._block("Build decision triggers (live persist)")
        self.assertNotIn("inputs.dry_run == true", live_block)

    def test_ambiguous_manual_inputs_rejected(self) -> None:
        block = self._block("Reject ambiguous manual live inputs")
        self.assertIn("inputs.dry_run == false && inputs.live_llm == false", block)
        self.assertIn("exit 1", block)

    def test_readiness_gate_always_present(self) -> None:
        self.assertIn("Verify live ops readiness", self.text)
        self.assertIn("check_live_readiness", self.text)

    def test_recommended_models_env_present(self) -> None:
        for key in (
            "COMPETITION_A_MAIN_MODEL",
            "COMPETITION_D_VALIDATOR_MODEL",
            "GEMINI_EVENT_ANALYZER_MODEL",
        ):
            self.assertIn(key, self.text)

    def test_workflow_korean_display_name(self) -> None:
        self.assertRegex(self.text, r"^name: AI 투자 경쟁 자동 운용", re.MULTILINE)

    def test_slack_test_input_present(self) -> None:
        self.assertIn("test_slack:", self.text)
        self.assertIn("Slack 연결 테스트 메시지 발송", self.text)

    def test_slack_test_step_gated(self) -> None:
        block = self._block("Send Slack connection test message")
        self.assertIn("inputs.test_slack == true", block)
        self.assertIn("test_competition_slack.py", block)

    def test_live_schedule_disabled_in_workflow(self) -> None:
        self.assertIn("LIVE schedule disabled", self.text)
        self.assertIsNone(re.search(r"^  schedule:\s*$", self.text, re.MULTILINE))

    def test_live_schedule_disabled_env(self) -> None:
        self.assertIn("COMPETITION_LIVE_SCHEDULE_DISABLED", self.text)
        session_block = self._block("Run competition session (live)")
        self.assertIn("inputs.test_slack != true", session_block)
        init_block = self._block("Init competition accounts (idempotent)")
        self.assertIn("inputs.test_slack != true", init_block)
        event_block = self._block("Event scan (no persist)")
        self.assertIn("inputs.test_slack != true", event_block)

    def test_replay_workflow_exists(self) -> None:
        p = ROOT / ".github" / "workflows" / "competition_replay_audit.yml"
        self.assertTrue(p.is_file())
        text = p.read_text(encoding="utf-8")
        self.assertIn("send_slack_reports", text)
        self.assertIn("short_5days", text)
        self.assertIn("full_audit", text)


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    unittest.main()
