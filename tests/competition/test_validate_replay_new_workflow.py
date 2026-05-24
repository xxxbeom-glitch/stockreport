# -*- coding: utf-8 -*-
"""New-campaign workflow validation script tests."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_replay_new_workflow.py"


class ValidateReplayNewWorkflowTests(unittest.TestCase):
    def _run(self, *args: str) -> int:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        return proc.returncode

    def test_month_ok(self) -> None:
        self.assertEqual(
            self._run("--replay-type", "month", "--start-date", "20260102"),
            0,
        )

    def test_invalid_type_fails(self) -> None:
        self.assertEqual(
            self._run("--replay-type", "full_audit", "--start-date", "20260102"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
