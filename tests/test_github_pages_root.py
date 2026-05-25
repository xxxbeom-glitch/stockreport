# -*- coding: utf-8
"""GitHub Pages root entry and staged artifact layout."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_INDEX = ROOT / "index.html"
DASHBOARD_INDEX = ROOT / "template" / "dashboard_desktop" / "index.html"


class GitHubPagesRootTest(unittest.TestCase):
    def test_root_and_dashboard_index_exist(self) -> None:
        self.assertTrue(ROOT_INDEX.is_file())
        self.assertTrue(DASHBOARD_INDEX.is_file())

    def test_root_redirects_to_replay_dashboard(self) -> None:
        text = ROOT_INDEX.read_text(encoding="utf-8")
        self.assertRegex(text, r"template/dashboard_desktop/\?mode=replay")

    def test_staged_artifact_layout(self) -> None:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.stage_replay_pages_artifact import stage_pages_artifact

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pages"
            stage_pages_artifact(out)
            self.assertTrue((out / "index.html").is_file())
            self.assertTrue((out / "template" / "dashboard_desktop" / "index.html").is_file())
            self.assertFalse((out / "src").exists())
            self.assertFalse((out / "tests").exists())


if __name__ == "__main__":
    unittest.main()
