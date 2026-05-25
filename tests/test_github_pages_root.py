# -*- coding: utf-8
"""GitHub Pages root entry and dashboard paths in deploy artifact."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_INDEX = ROOT / "index.html"
DASHBOARD_INDEX = ROOT / "template" / "dashboard_desktop" / "index.html"

# upload-pages-artifact path: . (repo root) — these must ship with Pages deploy.
PAGES_ARTIFACT_REQUIRED = (
    "index.html",
    "template/dashboard_desktop/index.html",
)


class GitHubPagesRootTest(unittest.TestCase):
    def test_root_and_dashboard_index_exist(self) -> None:
        self.assertTrue(ROOT_INDEX.is_file(), "root index.html missing")
        self.assertTrue(DASHBOARD_INDEX.is_file(), "dashboard index.html missing")

    def test_root_redirects_to_replay_dashboard(self) -> None:
        text = ROOT_INDEX.read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"template/dashboard_desktop/\?mode=replay",
        )

    def test_pages_artifact_includes_required_entrypoints(self) -> None:
        """Mirror replay workflow artifact (path: .) — root + dashboard HTML present."""
        missing = [rel for rel in PAGES_ARTIFACT_REQUIRED if not (ROOT / rel).is_file()]
        self.assertEqual(missing, [], f"Pages artifact would omit: {missing}")

    def test_workflows_upload_repo_root_for_pages(self) -> None:
        workflows = ROOT / ".github" / "workflows"
        replay_yml = sorted(workflows.glob("replay_*.yml"))
        self.assertGreaterEqual(len(replay_yml), 1)
        for path in replay_yml:
            text = path.read_text(encoding="utf-8")
            if "upload-pages-artifact" not in text:
                continue
            self.assertRegex(
                text,
                re.compile(r"upload-pages-artifact@v\d+[\s\S]*?path:\s*\.", re.MULTILINE),
                msg=f"{path.name} should upload repo root for Pages",
            )


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    unittest.main()
