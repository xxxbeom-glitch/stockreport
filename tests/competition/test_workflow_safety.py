# -*- coding: utf-8 -*-
"""Static checks for competition_auto_ops workflow (LIVE paused)."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "competition_auto_ops.yml"
REPLAY_WORKFLOW = ROOT / ".github" / "workflows" / "competition_replay_audit.yml"


class WorkflowSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_file_exists(self) -> None:
        self.assertTrue(WORKFLOW.is_file())

    def test_workflow_display_name_paused(self) -> None:
        self.assertIn("name: LIVE", self.text)
        self.assertIn("중지됨", self.text)

    def test_no_workflow_dispatch_inputs(self) -> None:
        self.assertRegex(self.text, r"on:\s*\n\s*workflow_dispatch:\s*\n", re.MULTILINE)
        self.assertIsNone(re.search(r"^\s+inputs:\s*$", self.text, re.MULTILINE))
        self.assertNotIn("dry_run:", self.text)
        self.assertNotIn("test_slack:", self.text)
        self.assertNotIn("reset_competition_seed:", self.text)

    def test_live_schedule_disabled(self) -> None:
        self.assertIn("COMPETITION_LIVE_SCHEDULE_DISABLED", self.text)
        self.assertIsNone(re.search(r"^  schedule:\s*$", self.text, re.MULTILINE))

    def test_readiness_only_on_dispatch(self) -> None:
        self.assertIn("LIVE auto-ops paused notice", self.text)
        self.assertIn("Verify live ops readiness", self.text)
        self.assertIn("check_live_readiness", self.text)
        self.assertIn("live_auto_ops_enabled", self.text)

    def test_no_live_session_on_dispatch(self) -> None:
        self.assertNotIn("run_competition_session", self.text)
        self.assertNotIn("init_competition_accounts", self.text)
        self.assertNotIn("reset_competition_seed", self.text)
        self.assertNotIn("test_competition_slack", self.text)
        self.assertNotIn("test_competition_market_closed_notice", self.text)
        self.assertNotIn("build_decision_triggers", self.text)
        self.assertNotIn("run_competition_event_scan", self.text)

    def test_restore_documentation_present(self) -> None:
        self.assertIn("Restore LIVE after REPLAY", self.text)
        self.assertIn("competition_replay_audit.yml", self.text)

    def test_slack_webhook_mapping_uses_trading_secret(self) -> None:
        self.assertIn(
            "COMPETITION_SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK_TRADING }}",
            self.text,
        )

    def test_no_mock_llm_or_local_mirror_env_set(self) -> None:
        self.assertIsNone(
            re.search(r"^\s*COMPETITION_USE_MOCK_LLM:", self.text, re.MULTILINE),
        )
        self.assertIsNone(
            re.search(r"^\s*COMPETITION_ALLOW_LOCAL_MIRROR:", self.text, re.MULTILINE),
        )

    def test_replay_workflow_exists_for_validation(self) -> None:
        self.assertTrue(REPLAY_WORKFLOW.is_file())
        replay = REPLAY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("send_slack_reports", replay)
        self.assertIn("short_5days", replay)
        self.assertIn("run_competition_replay.py", replay)
        self.assertIn("Run REPLAY (resume existing campaign)", replay)
        self.assertIn("inputs.resume_existing_campaign == true", replay)
        self.assertIn("deploy-pages@v4", replay)
        self.assertNotIn("${{ inputs.resume_existing_campaign }}\" = \"true\"", replay)
        self.assertRegex(
            replay,
            r'^name:\s+"REPLAY · 과거 투자 검증"',
            re.MULTILINE,
        )
        self.assertNotRegex(
            replay,
            r"uses:\s+actions/deploy-pages@v4\n\s+if:.*\n\s+environment:",
            re.MULTILINE,
        )


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    unittest.main()
