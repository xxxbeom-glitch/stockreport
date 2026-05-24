"""Dashboard REPLAY payload — isolated from LIVE data."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.trading.competition.dashboard.payload import build_dashboard_payload
from src.trading.competition.dashboard.replay_payload import (
    build_replay_dashboard_payload,
    list_replay_runs,
)

ROOT = Path(__file__).resolve().parents[2]
REPLAY_ROOT = ROOT / "data" / "competition" / "replay"


class ReplayDashboardPayloadTests(unittest.TestCase):
    def test_list_replay_runs_non_empty_when_data_present(self) -> None:
        if not REPLAY_ROOT.is_dir():
            self.skipTest("no replay data")
        runs = list_replay_runs()
        self.assertTrue(runs)
        self.assertIn("replayRunId", runs[0])

    def test_replay_payload_isolated_from_live(self) -> None:
        runs = list_replay_runs()
        if not runs:
            self.skipTest("no replay runs")
        run_id = runs[0]["replayRunId"]
        replay = build_replay_dashboard_payload(run_id)
        live = build_dashboard_payload()

        self.assertEqual(replay["dataSource"], "replay")
        self.assertEqual(live["dataSource"], "live")
        self.assertEqual(replay["replayRunId"], run_id)
        self.assertIn("auditSummary", replay)
        self.assertIn("teamDecisions", replay)
        self.assertNotIn("auditSummary", live)

    def test_replay_manifest_roundtrip(self) -> None:
        for manifest_path in REPLAY_ROOT.glob("*/manifest.json"):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            run_id = manifest["replay_run_id"]
            payload = build_replay_dashboard_payload(run_id)
            self.assertEqual(payload["replayMeta"]["tradingDate"], manifest.get("trading_date"))
            self.assertEqual(payload["auditSummary"]["leakageStatus"], manifest.get("leakage_summary"))
            return
        self.skipTest("no manifest")


if __name__ == "__main__":
    unittest.main()
