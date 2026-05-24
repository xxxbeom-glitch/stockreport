"""Public dashboard base URL for Slack / Actions."""

from __future__ import annotations

import os
import unittest

from src.trading.competition.replay.firestore_store import (
    GITHUB_PAGES_DASHBOARD_BASE,
    replay_dashboard_base_url,
    replay_report_url,
)


class ReplayDashboardUrlTests(unittest.TestCase):
    def test_default_base_is_github_pages(self) -> None:
        env = os.environ.copy()
        for key in ("COMPETITION_DASHBOARD_BASE_URL", "DASHBOARD_BASE_URL"):
            env.pop(key, None)
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(replay_dashboard_base_url(), GITHUB_PAGES_DASHBOARD_BASE)

    def test_report_url_uses_base(self) -> None:
        with unittest.mock.patch.dict(
            os.environ,
            {"COMPETITION_DASHBOARD_BASE_URL": "https://example.com/app"},
            clear=False,
        ):
            url = replay_report_url(
                campaign_id="camp1",
                report_key="w50",
                report_type="weekly",
                replay_run_id="replay_x",
            )
        self.assertTrue(url.startswith("https://example.com/app/template/dashboard_desktop/"))
        self.assertIn("mode=replay", url)
        self.assertIn("campaign=camp1", url)


import unittest.mock

if __name__ == "__main__":
    unittest.main()
