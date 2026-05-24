# -*- coding: utf-8 -*-
"""Workflow input validation script tests."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_replay_workflow_inputs.py"


class ValidateReplayWorkflowInputsTests(unittest.TestCase):
    def _run(self, *args: str) -> int:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        return proc.returncode

    def test_campaign_id_without_resume_fails(self) -> None:
        code = self._run("--resume", "false", "--campaign-id", "month_20260102_20260130_1b51cb")
        self.assertEqual(code, 1)

    def test_resume_without_campaign_id_fails(self) -> None:
        code = self._run("--resume", "true", "--campaign-id", "")
        self.assertEqual(code, 1)

    def test_resume_with_campaign_id_ok(self) -> None:
        code = self._run("--resume", "true", "--campaign-id", "month_20260102_20260130_1b51cb")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
