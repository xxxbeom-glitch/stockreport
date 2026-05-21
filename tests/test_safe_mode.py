"""SAFE_MODE — watchlist·Slack·스케줄 게이트 테스트."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.weekly_watchlist_update.watchlist_apply import (
    apply_watchlist_from_proposal,
)
from data.kr_watchlist import load_kr_watchlist_raw, save_kr_watchlist_raw
from utils import safe_mode


class TestSafeModeFlags(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)
        load_kr_watchlist_raw.cache_clear()

    def test_defaults_block_auto_actions(self) -> None:
        os.environ.pop("SAFE_MODE", None)
        os.environ.pop("WATCHLIST_AUTO_APPLY", None)
        os.environ.pop("SLACK_AUTO_SEND", None)
        self.assertTrue(safe_mode.is_safe_mode())
        self.assertFalse(safe_mode.watchlist_auto_apply_enabled())
        self.assertFalse(safe_mode.slack_auto_send_enabled())
        self.assertFalse(safe_mode.can_apply_watchlist(explicit_cli=False))
        self.assertFalse(safe_mode.can_apply_watchlist(explicit_cli=True))
        self.assertFalse(safe_mode.can_send_slack(explicit_cli=True))

    def test_explicit_send_when_env_enabled(self) -> None:
        os.environ["SAFE_MODE"] = "true"
        os.environ["SLACK_AUTO_SEND"] = "true"
        self.assertTrue(safe_mode.can_send_slack(explicit_cli=True))

    def test_banner_lines(self) -> None:
        lines: list[str] = []
        safe_mode.print_safe_mode_banner(emit=lines.append)
        joined = "\n".join(lines)
        self.assertIn("watchlist auto apply disabled", joined)
        self.assertIn("slack auto send disabled", joined)
        self.assertIn("candidate auto replace disabled", joined)


class TestWatchlistNotModified(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()
        os.environ["SAFE_MODE"] = "true"
        os.environ["WATCHLIST_AUTO_APPLY"] = "false"
        load_kr_watchlist_raw.cache_clear()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)
        load_kr_watchlist_raw.cache_clear()

    def test_save_without_apply_returns_false(self) -> None:
        before = load_kr_watchlist_raw()
        ok = save_kr_watchlist_raw({"version": 99, "sectors": {}}, explicit_apply=True)
        after = load_kr_watchlist_raw()
        self.assertFalse(ok)
        self.assertEqual(before, after)

    def test_apply_watchlist_without_flag_is_proposal_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proposal = Path(tmp) / "p.json"
            before = load_kr_watchlist_raw()
            proposal.write_text(
                json.dumps({"watchlist": before}, ensure_ascii=False),
                encoding="utf-8",
            )
            result = apply_watchlist_from_proposal(proposal, apply=True)
            self.assertFalse(result.get("applied"))
            self.assertEqual(load_kr_watchlist_raw(), before)

    def test_apply_false_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proposal = Path(tmp) / "p.json"
            before = load_kr_watchlist_raw()
            proposal.write_text("{}", encoding="utf-8")
            result = apply_watchlist_from_proposal(proposal, apply=False)
            self.assertFalse(result.get("applied"))
            self.assertEqual(load_kr_watchlist_raw(), before)


class TestWorkflowCronDisabled(unittest.TestCase):
    def test_weekly_workflow_has_no_active_schedule(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "weekly_watchlist.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", text)
        self.assertNotRegex(text, r"^\s+schedule:\s*$", text)
        self.assertIn("# schedule:", text)

    def test_intraday_workflow_has_no_active_schedule(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "kr_intraday_slack.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("# schedule:", text)
        lines = text.splitlines()
        active_cron = [
            ln
            for ln in lines
            if "cron:" in ln and not ln.strip().startswith("#")
        ]
        self.assertEqual(active_cron, [])


class TestPipelineSlackGate(unittest.TestCase):
    def test_pipeline_skips_slack_when_not_allowed(self) -> None:
        os.environ["SAFE_MODE"] = "true"
        os.environ["SLACK_AUTO_SEND"] = "false"
        fake_metric = {
            "symbol": "테스트",
            "ticker": "000001",
            "sector_name": "반도체 소재",
            "data_status": "ok",
            "return_5d": 1.0,
            "tv_growth_5d_vs_10d": 0.1,
            "recent_slack_sent_count": 0,
        }
        with patch(
            "agents.weekly_watchlist_update.pipeline.collect_weekly_metrics",
            return_value=[fake_metric],
        ):
            with patch(
                "agents.weekly_watchlist_update.pipeline.judge_weekly_sector_mood",
                return_value={"반도체 소재": "neutral"},
            ):
                with patch(
                    "agents.weekly_watchlist_update.pipeline.run_weekly_review",
                    return_value=({"stocks": [], "summary": ""}, None),
                ):
                    with patch(
                        "slack_sender.post_message",
                    ) as post_mock:
                        from agents.weekly_watchlist_update.pipeline import (
                            run_weekly_watchlist_update,
                        )

                        result = run_weekly_watchlist_update(
                            send_slack=True,
                            send_slack_explicit=True,
                        )
        self.assertFalse(result.slack_sent)
        post_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
