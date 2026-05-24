"""CI workflow helpers for REPLAY JSON output."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import replay_workflow_outputs as rwo
from scripts import run_competition_replay as rcr


class ReplayResultFileTests(unittest.TestCase):
    def test_result_out_writes_pure_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "replay_result.json"
            payload = {"ok": True, "campaign_id": "month_x", "needs_resume": True}
            out.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            loaded = rwo._load_result(out)
            self.assertEqual(loaded["campaign_id"], "month_x")

    def test_workflow_outputs_github_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / "replay_result.json"
            result.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "campaign_id": "month_20260102_20260130_abc123",
                        "needs_resume": True,
                        "progress_label": "1월 리플레이 진행 중 · 5 / 21 거래일 완료",
                    }
                ),
                encoding="utf-8",
            )
            gh_out = Path(tmp) / "github_output.txt"
            summary = Path(tmp) / "summary.md"
            with mock.patch.dict(
                "os.environ",
                {"GITHUB_OUTPUT": str(gh_out), "GITHUB_STEP_SUMMARY": str(summary)},
                clear=False,
            ):
                import sys

                old_argv = sys.argv
                sys.argv = ["replay_workflow_outputs.py", str(result)]
                try:
                    self.assertEqual(rwo.main(), 0)
                finally:
                    sys.argv = old_argv
            text = gh_out.read_text(encoding="utf-8")
            self.assertIn("ok=true", text)
            self.assertIn("campaign_id=month_20260102_20260130_abc123", text)
            self.assertIn("needs_resume=true", text)
            self.assertIn("month_20260102_20260130_abc123", summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
