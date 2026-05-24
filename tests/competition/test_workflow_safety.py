# -*- coding: utf-8 -*-
"""Static checks for competition workflows (LIVE paused + REPLAY user-facing)."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
LIVE_WORKFLOW = WORKFLOWS / "competition_auto_ops.yml"
REPLAY_NEW = WORKFLOWS / "replay_new_campaign.yml"
REPLAY_RESUME = WORKFLOWS / "replay_resume_campaign.yml"


class WorkflowSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.live_text = LIVE_WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_file_exists(self) -> None:
        self.assertTrue(LIVE_WORKFLOW.is_file())

    def test_only_user_facing_workflow_files(self) -> None:
        yml_files = sorted(p.name for p in WORKFLOWS.glob("*.yml"))
        self.assertEqual(
            yml_files,
            ["competition_auto_ops.yml", "replay_new_campaign.yml", "replay_resume_campaign.yml"],
        )

    def test_removed_workflows_deleted(self) -> None:
        for name in (
            "competition_replay_audit.yml",
            "replay_dev_manual.yml",
            "deploy-dashboard-pages.yml",
        ):
            self.assertFalse((WORKFLOWS / name).is_file(), msg=name)

    def test_workflow_display_name_paused(self) -> None:
        self.assertIn('name: "LIVE - 실시간 투자 운용 (현재 중지)"', self.live_text)

    def test_no_workflow_dispatch_inputs_on_live(self) -> None:
        self.assertRegex(self.live_text, r"on:\s*\n\s*workflow_dispatch:\s*\n", re.MULTILINE)
        self.assertIsNone(re.search(r"^\s+inputs:\s*$", self.live_text, re.MULTILINE))
        self.assertNotIn("dry_run:", self.live_text)
        self.assertNotIn("test_slack:", self.live_text)
        self.assertNotIn("reset_competition_seed:", self.live_text)

    def test_live_schedule_disabled(self) -> None:
        self.assertIn("COMPETITION_LIVE_SCHEDULE_DISABLED", self.live_text)
        self.assertIsNone(re.search(r"^  schedule:\s*$", self.live_text, re.MULTILINE))

    def test_readiness_only_on_dispatch(self) -> None:
        self.assertIn("LIVE auto-ops paused notice", self.live_text)
        self.assertIn("Verify live ops readiness", self.live_text)
        self.assertIn("check_live_readiness", self.live_text)
        self.assertIn("live_auto_ops_enabled", self.live_text)

    def test_no_live_session_on_dispatch(self) -> None:
        self.assertNotIn("run_competition_session", self.live_text)
        self.assertNotIn("init_competition_accounts", self.live_text)
        self.assertNotIn("reset_competition_seed", self.live_text)
        self.assertNotIn("test_competition_slack", self.live_text)
        self.assertNotIn("test_competition_market_closed_notice", self.live_text)
        self.assertNotIn("build_decision_triggers", self.live_text)
        self.assertNotIn("run_competition_event_scan", self.live_text)

    def test_restore_documentation_present(self) -> None:
        self.assertIn("Restore LIVE after REPLAY", self.live_text)
        self.assertIn("replay_new_campaign.yml", self.live_text)

    def test_slack_webhook_mapping_uses_trading_secret(self) -> None:
        self.assertIn(
            "COMPETITION_SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK_TRADING }}",
            self.live_text,
        )

    def test_replay_new_workflow(self) -> None:
        self.assertTrue(REPLAY_NEW.is_file())
        text = REPLAY_NEW.read_text(encoding="utf-8")
        self.assertIn('name: "REPLAY - 새로 시작"', text)
        self.assertIn("run_competition_replay.py", text)
        self.assertIn("publish_replay_pages_data.py", text)
        self.assertIn("deploy-pages@v4", text)
        self.assertNotIn("resume-existing-campaign", text)
        self.assertNotIn("resume_existing_campaign", text)

    def test_replay_resume_workflow(self) -> None:
        self.assertTrue(REPLAY_RESUME.is_file())
        text = REPLAY_RESUME.read_text(encoding="utf-8")
        self.assertIn('name: "REPLAY - 이어서 실행"', text)
        self.assertIn("select_resumable_replay_campaign.py", text)
        self.assertIn("--resume-existing-campaign", text)
        self.assertIn("publish_replay_pages_data.py", text)
        self.assertIn("deploy-pages@v4", text)
        self.assertNotIn("inputs:\n      replay_type:", text)


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    unittest.main()
