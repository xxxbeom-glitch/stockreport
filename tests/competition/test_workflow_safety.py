# -*- coding: utf-8
"""Static checks for unified REPLAY workflow."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
REPLAY_YML = WORKFLOWS / "replay.yml"


class ReplayWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = REPLAY_YML.read_text(encoding="utf-8")

    def test_only_replay_workflow_file(self) -> None:
        yml_files = sorted(p.name for p in WORKFLOWS.glob("*.yml"))
        self.assertEqual(yml_files, ["replay.yml"])

    def test_display_name(self) -> None:
        self.assertIn('name: "REPLAY - 실행"', self.text)

    def test_dispatch_and_schedule_triggers(self) -> None:
        self.assertIn("workflow_dispatch:", self.text)
        self.assertRegex(self.text, r"schedule:\s*\n\s*-\s*cron:", re.MULTILINE)
        self.assertIn('cron: "*/10 * * * *"', self.text)

    def test_concurrency_lock(self) -> None:
        self.assertIn("group: replay-campaign", self.text)
        self.assertIn("cancel-in-progress: false", self.text)

    def test_kis_safety_env(self) -> None:
        self.assertIn("KIS_MAX_REQUESTS_PER_SECOND", self.text)
        self.assertIn("KIS_ENRICH_MAX_WORKERS", self.text)
        self.assertIn("KIS_MAX_REQUESTS_PER_RUN", self.text)

    def test_new_and_resume_paths(self) -> None:
        self.assertIn("run_mode=new", self.text)
        self.assertIn("run_mode=resume", self.text)
        self.assertIn("select_resumable_replay_campaign.py", self.text)
        self.assertIn("--resume-existing-campaign", self.text)
        self.assertIn("id: replay_new_run", self.text)
        self.assertIn("id: replay_resume_run", self.text)
        self.assertNotIn("resume-existing-campaign", self.text.replace("--resume-existing-campaign", ""))

    def test_no_duplicate_step_ids(self) -> None:
        import re

        ids = re.findall(r"^\s+id:\s+(\S+)\s*$", self.text, re.MULTILINE)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dupes, [], f"duplicate step ids: {dupes}")
        self.assertNotIn("replay_run", ids)

    def test_pages_staging_not_full_repo(self) -> None:
        self.assertIn("stage_replay_pages_artifact.py", self.text)
        self.assertIn("path: _pages_staging", self.text)
        self.assertNotRegex(
            self.text,
            re.compile(r"upload-pages-artifact@v\d+[\s\S]*?path:\s*\.\s*$", re.MULTILINE),
        )

    def test_removed_legacy_workflows(self) -> None:
        for name in (
            "competition_auto_ops.yml",
            "replay_new_campaign.yml",
            "replay_resume_campaign.yml",
            "replay_auto_resume.yml",
            "deploy-dashboard-pages.yml",
        ):
            self.assertFalse((WORKFLOWS / name).is_file(), msg=name)


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    unittest.main()
