# -*- coding: utf-8
"""REPLAY / AUDIT system tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.replay.evidence import EvidenceRecord, evidence_usable_for_decision, make_price_evidence
from src.trading.competition.replay.leakage_audit import audit_evidence_list
from src.trading.competition.runtime import assert_live_session_allowed, is_replay_mode, replay_run_dir


class ReplayAuditSystemTest(unittest.TestCase):
    def test_future_evidence_blocked(self) -> None:
        rec = EvidenceRecord(
            evidence_id="e1",
            source_type="price",
            observed_at="2026-05-23T15:30:00+09:00",
            published_at="2026-05-23T15:30:00+09:00",
            available_at="2026-05-23T15:30:00+09:00",
            fetched_at="2026-05-22T15:30:00+09:00",
            decision_at="2026-05-22T15:30:00+09:00",
            timestamp_confidence="verified",
        )
        audit = audit_evidence_list([rec], decision_at="2026-05-22T15:30:00+09:00", core_evidence_ids=["e1"])
        self.assertEqual(audit["status"], "FAIL")
        self.assertFalse(audit["decision_valid"])

    def test_verified_price_evidence_passes(self) -> None:
        rec = make_price_evidence(
            evidence_id="price:005930:20260522",
            ticker="005930",
            decision_at="2026-05-22T15:30:00+09:00",
            trading_date="20260522",
            close_krw=56000,
        )
        self.assertTrue(evidence_usable_for_decision(rec))
        audit = audit_evidence_list(
            [rec],
            decision_at="2026-05-22T15:30:00+09:00",
            core_evidence_ids=[rec.evidence_id],
        )
        self.assertEqual(audit["status"], "PASS")

    def test_live_session_blocked_when_schedule_disabled(self) -> None:
        env = os.environ.copy()
        env["COMPETITION_EXECUTION_MODE"] = "live"
        env["COMPETITION_LIVE_SCHEDULE_DISABLED"] = "1"
        env.pop("COMPETITION_ALLOW_LIVE_SESSION", None)
        with self.assertRaises(RuntimeError):
            with unittest.mock.patch.dict(os.environ, env, clear=False):
                assert_live_session_allowed()

    def test_replay_mode_blocks_live_session(self) -> None:
        with unittest.mock.patch.dict(os.environ, {"COMPETITION_EXECUTION_MODE": "replay_smoke"}, clear=False):
            self.assertTrue(is_replay_mode())
            with self.assertRaises(RuntimeError):
                assert_live_session_allowed()

    def test_replay_run_dir_under_replay_namespace(self) -> None:
        p = replay_run_dir("test_run_001")
        self.assertIn("replay", str(p).replace("\\", "/"))
        self.assertNotIn("live", p.name)

    def test_workflow_live_schedule_disabled(self) -> None:
        wf = (ROOT / ".github" / "workflows" / "competition_auto_ops.yml").read_text(encoding="utf-8")
        self.assertIn("COMPETITION_LIVE_SCHEDULE_DISABLED", wf)
        self.assertIn("PAUSED until REPLAY", wf)
        self.assertIsNone(re.search(r"^  schedule:\s*$", wf, re.MULTILINE))

    def test_replay_workflows_exist(self) -> None:
        for name in ("replay_new_campaign.yml", "replay_resume_campaign.yml"):
            p = ROOT / ".github" / "workflows" / name
            self.assertTrue(p.is_file(), msg=name)
            text = p.read_text(encoding="utf-8")
            self.assertIn("COMPETITION_SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK_TRADING }}", text)
            self.assertIn("replay_smoke", text)
            self.assertIn("deploy-pages@v4", text)


import re
import unittest.mock

if __name__ == "__main__":
    unittest.main()
