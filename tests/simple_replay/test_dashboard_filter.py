"""Dashboard index only exposes completed runs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.trading.simple_replay.publish import rebuild_index
from src.trading.simple_replay.paths import SIMPLE_REPLAY_RUNS_DIR


class DashboardFilterTests(unittest.TestCase):
    def test_index_skips_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            runs.mkdir()
            ok_run = runs / "simple_replay_20260102_abc"
            ok_run.mkdir()
            (ok_run / "manifest.json").write_text(
                json.dumps({"run_id": "simple_replay_20260102_abc", "status": "completed", "decision_date": "20260102"}),
                encoding="utf-8",
            )
            bad = runs / "simple_replay_20260102_fail"
            bad.mkdir()
            (bad / "manifest.json").write_text(
                json.dumps({"run_id": "simple_replay_20260102_fail", "status": "failed"}),
                encoding="utf-8",
            )
            import src.trading.simple_replay.paths as pp
            import src.trading.simple_replay.publish as pub

            old_runs = pp.SIMPLE_REPLAY_RUNS_DIR
            old_pages = pp.SIMPLE_REPLAY_PAGES_ROOT
            old_pub_pages = pub.SIMPLE_REPLAY_PAGES_ROOT
            try:
                pp.SIMPLE_REPLAY_RUNS_DIR = runs
                pages = root / "pages"
                pp.SIMPLE_REPLAY_PAGES_ROOT = pages
                pub.SIMPLE_REPLAY_PAGES_ROOT = pages
                rebuild_index()
                idx = json.loads((root / "pages" / "index.json").read_text(encoding="utf-8"))
                self.assertEqual(len(idx["runs"]), 1)
                self.assertEqual(idx["runs"][0]["runId"], "simple_replay_20260102_abc")
            finally:
                pp.SIMPLE_REPLAY_RUNS_DIR = old_runs
                pp.SIMPLE_REPLAY_PAGES_ROOT = old_pages
                pub.SIMPLE_REPLAY_PAGES_ROOT = old_pub_pages


if __name__ == "__main__":
    unittest.main()
