"""플래그 분리 — DAILY_PICK vs WATCHLIST_REVIEW."""

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


class TestDailyPickFlags(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_daily_pick_auto_send_default_true(self) -> None:
        os.environ.pop("DAILY_PICK_AUTO_SEND", None)
        self.assertTrue(safe_mode.daily_pick_auto_send_enabled())

    def test_daily_pick_send_not_blocked_by_safe_mode(self) -> None:
        os.environ["SAFE_MODE"] = "true"
        os.environ.pop("DAILY_PICK_AUTO_SEND", None)
        self.assertTrue(
            safe_mode.can_send_daily_pick_slack(explicit_cli=True, scheduled=True)
        )

    def test_daily_pick_banner_enabled(self) -> None:
        os.environ["DAILY_PICK_AUTO_SEND"] = "true"
        lines: list[str] = []
        safe_mode.print_daily_pick_status(emit=lines.append)
        self.assertIn("[DAILY_PICK] Slack 발송 가능", lines)


class TestWatchlistReviewFlags(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()
        os.environ["WATCHLIST_REVIEW_AUTO_SEND"] = "false"
        os.environ["WATCHLIST_AUTO_APPLY"] = "false"
        os.environ["CANDIDATE_AUTO_REPLACE"] = "false"
        load_kr_watchlist_raw.cache_clear()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)
        load_kr_watchlist_raw.cache_clear()

    def test_watchlist_review_send_default_false(self) -> None:
        os.environ.pop("WATCHLIST_REVIEW_AUTO_SEND", None)
        self.assertFalse(safe_mode.watchlist_review_auto_send_enabled())
        self.assertFalse(safe_mode.can_send_watchlist_review_slack(explicit_cli=True))

    def test_watchlist_review_banner(self) -> None:
        lines: list[str] = []
        safe_mode.print_watchlist_review_status(emit=lines.append)
        joined = "\n".join(lines)
        self.assertIn("[WATCHLIST_REVIEW] 자동 발송 중지", joined)
        self.assertIn("[WATCHLIST_REVIEW] 자동 수정 중지", joined)
        self.assertIn("[CANDIDATES] 자동 교체 중지", joined)

    def test_save_without_apply_returns_false(self) -> None:
        before = load_kr_watchlist_raw()
        ok = save_kr_watchlist_raw({"version": 99, "sectors": {}}, explicit_apply=True)
        after = load_kr_watchlist_raw()
        self.assertFalse(ok)
        self.assertEqual(before, after)

    def test_apply_watchlist_blocked_without_env(self) -> None:
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


class TestWorkflowSchedules(unittest.TestCase):
    def test_daily_pick_workflow_has_active_schedule(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "daily_pick_alert.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("name: 매일 투자 후보 알림", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("\n  schedule:\n", text)
        active_cron = [
            ln
            for ln in text.splitlines()
            if "cron:" in ln and not ln.strip().startswith("#")
        ]
        self.assertGreaterEqual(len(active_cron), 2)
        self.assertIn('DAILY_PICK_AUTO_SEND: "true"', text)

    def test_watchlist_review_workflow_has_no_active_schedule(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "watchlist_review.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("# schedule:", text)
        active_cron = [
            ln
            for ln in text.splitlines()
            if "cron:" in ln and not ln.strip().startswith("#")
        ]
        self.assertEqual(active_cron, [])
        self.assertIn('WATCHLIST_REVIEW_AUTO_SEND: "false"', text)

    def test_candidate_scan_workflow_manual_only(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "candidate_scan_test.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("name: 신규 후보 스캔 테스트", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("\n  schedule:\n", text)


class TestPipelineSlackGate(unittest.TestCase):
    def test_pipeline_skips_watchlist_review_slack_by_default(self) -> None:
        os.environ["WATCHLIST_REVIEW_AUTO_SEND"] = "false"
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
                    with patch("slack_sender.post_message") as post_mock:
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
