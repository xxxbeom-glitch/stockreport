"""Public REPLAY JSON publish for GitHub Pages."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.trading.competition.replay import pages_publish as pp


class PagesPublishTests(unittest.TestCase):
    def test_sanitize_strips_firestore_sync(self) -> None:
        raw = {
            "dataSource": "replay",
            "firestore_sync": {"ok": True},
            "replayMeta": {"firestoreSync": {"x": 1}, "tradingDate": "20241218"},
        }
        safe = pp.sanitize_dashboard_payload(raw)
        self.assertNotIn("firestore_sync", safe)
        self.assertNotIn("firestoreSync", safe.get("replayMeta", {}))

    def test_rebuild_index_lists_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs" / "replay_test" / "dashboard.json"
            runs.parent.mkdir(parents=True)
            runs.write_text(
                json.dumps(
                    {
                        "replayMeta": {"tradingDate": "20241218"},
                        "campaignId": "camp_x",
                        "auditSummary": {"leakageStatus": "clean"},
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(pp, "REPLAY_DATA_ROOT", root):
                with mock.patch.object(pp, "LOCAL_REPLAY_ROOT", root):
                    index = pp.rebuild_index()
            self.assertEqual(len(index["runs"]), 1)
            self.assertEqual(index["runs"][0]["replayRunId"], "replay_test")


if __name__ == "__main__":
    unittest.main()
