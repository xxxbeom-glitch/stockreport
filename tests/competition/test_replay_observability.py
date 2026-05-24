"""REPLAY observability — redaction and public audit summaries."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.trading.competition.replay.observability import (
    RunObservability,
    build_public_audit_summary,
    compute_strategy_differentiation,
    redact_record,
    workflow_run_context,
)


class ObservabilityRedactionTests(unittest.TestCase):
    def test_redact_secrets_in_values(self) -> None:
        rec = {
            "api_key": "should-redact-key-name",
            "url": "https://hooks.slack.com/services/xxx/yyy/zzz",
            "note": "ok",
        }
        safe = redact_record(rec)
        self.assertEqual(safe["api_key"], "[REDACTED]")
        self.assertEqual(safe["url"], "[REDACTED]")
        self.assertEqual(safe["note"], "ok")

    def test_workflow_context_has_no_tokens(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"GITHUB_RUN_ID": "999", "GITHUB_TOKEN": "ghp_secret_should_not_appear"},
            clear=False,
        ):
            ctx = workflow_run_context()
        self.assertEqual(ctx.get("github_run_id"), "999")
        self.assertNotIn("GITHUB_TOKEN", ctx)


class StrategyDifferentiationTests(unittest.TestCase):
    def test_divergence_when_teams_differ(self) -> None:
        decisions = [
            {"decision": {"team_id": "A", "action": "BUY", "ticker": "005930"}, "review": None},
            {"decision": {"team_id": "B", "action": "HOLD"}, "review": None},
            {"decision": {"team_id": "C", "action": "BUY", "ticker": "000660"}, "review": {"result": "APPROVE"}},
            {"decision": {"team_id": "D", "action": "WAIT"}, "review": {"result": "HOLD"}},
        ]
        diff = compute_strategy_differentiation(decisions)
        self.assertGreater(diff["unique_action_profiles"], 1)
        self.assertGreater(diff["divergence_score"], 0)


class RunObservabilityTests(unittest.TestCase):
    def test_finalize_writes_public_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "replay" / "replay_20260102_test01"
            root.mkdir(parents=True)
            with mock.patch(
                "src.trading.competition.replay.observability.replay_run_dir",
                return_value=root,
            ):
                obs = RunObservability(
                    "replay_20260102_test01",
                    campaign_id="camp_x",
                    replay_type="month",
                    trading_date="20260102",
                )
                obs.log_pipeline("snapshot_build", "ok")
                meta = obs.finalize(
                    {
                        "ok": True,
                        "leakage_summary": "PASS",
                        "code_audit_failures": 0,
                        "cost_model": "costs_not_implemented",
                        "costs_applied": False,
                        "committee": {"skipped": True},
                    },
                    status="completed",
                    strategy_diff=compute_strategy_differentiation([]),
                    force_mock=True,
                )
                public = obs.load_public_audit_summary()
            self.assertEqual(meta["status"], "completed")
            self.assertFalse(public.get("affectsLiveAccount"))
            self.assertEqual(public.get("leakageStatus"), "PASS")
            self.assertIn("pipelineHealth", public)
            self.assertTrue((root / "observability" / "execution_meta.json").is_file())
            self.assertTrue((root / "observability" / "pipeline_events.jsonl").is_file())

    def test_public_summary_from_meta(self) -> None:
        public = build_public_audit_summary(
            {
                "status": "partial",
                "providers": {"kis_configured": True, "pykrx_available": True},
                "strategy_differentiation": {
                    "divergence_score": 0.75,
                    "unique_action_profiles": 3,
                    "teams_evaluated": 4,
                },
                "pipeline_event_count": 12,
                "error_summaries": [],
                "cost_model": "not_implemented",
            },
            {"leakage_summary": "PASS", "code_audit_failures": 0, "committee": {"skipped": True}},
        )
        self.assertEqual(public["pipelineHealth"], "ok")
        self.assertEqual(public["strategyDifferentiation"]["divergenceScore"], 0.75)


if __name__ == "__main__":
    unittest.main()
