# -*- coding: utf-8
"""REPLAY batch checkpoint, KIS request budget, auto-resume selection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from data import kis_rate_limit as krl
from src.trading.competition.replay import batch_checkpoint as bc
from src.trading.competition.replay.campaign_resume import (
    init_campaign_manifest,
    load_manifest,
    save_checkpoint,
    save_manifest,
)
from src.trading.competition.replay.campaign_select import (
    list_auto_resumable_campaigns,
    resumability_exclusion_reason,
)


class BatchCheckpointHelpersTest(unittest.TestCase):
    def test_apply_request_budget_checkpoint(self) -> None:
        manifest = bc.apply_request_budget_checkpoint(
            {"campaign_id": "c1", "days_completed": 5},
            campaign_id="c1",
            chunk_processed_dates=["20260108"],
        )
        self.assertTrue(manifest["ok"])
        self.assertTrue(manifest["needs_resume"])
        self.assertEqual(manifest["competition_status"], bc.STATUS_CHECKPOINT_WAITING)
        self.assertEqual(manifest["resume_reason"], bc.RESUME_REASON_BUDGET)
        self.assertIsNone(manifest["error"])
        self.assertEqual(manifest["public_status"], "자동 재개 대기")

    def test_budget_vs_rate_limit_distinction(self) -> None:
        budget = {"batch_status": bc.STATUS_CHECKPOINT_WAITING, "error": bc.RESUME_REASON_BUDGET}
        rate = {"batch_status": bc.STATUS_RATE_LIMIT_PAUSED, "error": bc.RESUME_REASON_RATE_LIMIT}
        self.assertTrue(bc.is_budget_checkpoint_result(budget))
        self.assertFalse(bc.is_rate_limit_pause_result(budget))
        self.assertTrue(bc.is_rate_limit_pause_result(rate))
        self.assertFalse(bc.is_budget_checkpoint_result(rate))

    def test_fatal_stops_auto_resume(self) -> None:
        manifest = bc.apply_fatal_stop(
            {},
            campaign_id="c1",
            error="kis_auth_failed",
            failed_trading_date="20260109",
        )
        self.assertFalse(bc.should_auto_resume(manifest))
        self.assertEqual(manifest["public_status"], "확인 필요 오류")


class KISRequestBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        krl.reset_kis_rate_limit_state()

    def test_budget_reached_stops_without_http_call(self) -> None:
        with mock.patch.dict("os.environ", {"KIS_MAX_REQUESTS_PER_RUN": "3"}, clear=False):
            krl.reset_kis_rate_limit_state()
            with mock.patch("data.kis_rate_limit.requests.request") as mock_req:
                for _ in range(5):
                    krl.kis_http_request("GET", "https://example.com", tr_id="T")
            self.assertEqual(mock_req.call_count, 3)
            self.assertTrue(krl.is_kis_request_budget_reached())
            summary = krl.kis_rate_limit_observability()
            self.assertEqual(summary["kis_requests_used"], 3)
            self.assertTrue(summary["request_budget_reached"])

    def test_halt_vs_budget(self) -> None:
        krl.reset_kis_rate_limit_state()
        krl._rate_limit_state.halted = True
        with mock.patch("data.kis_rate_limit.requests.request") as mock_req:
            out = krl.kis_http_request("GET", "https://example.com")
        mock_req.assert_not_called()
        self.assertIsNone(out)
        self.assertFalse(krl.is_kis_request_budget_reached())


class CampaignResumeSelectionTest(unittest.TestCase):
    def _seed_campaign(
        self,
        camps_root: Path,
        campaign_id: str,
        *,
        status: str,
        needs_resume: bool,
        days_completed: int,
        days_total: int,
    ) -> None:
        planned = [f"202601{i:02d}" for i in range(2, 2 + days_total)]
        manifest = init_campaign_manifest(
            campaign_id=campaign_id,
            replay_type="month",
            planned_dates=planned,
            chunk_size=1,
            period_start=planned[0],
            period_end=planned[-1],
        )
        manifest["competition_status"] = status
        manifest["batch_status"] = status
        manifest["needs_resume"] = needs_resume
        manifest["days_completed"] = days_completed
        manifest["days_total"] = days_total
        manifest["planned_trading_dates"] = planned
        manifest["next_trading_date"] = planned[days_completed] if days_completed < days_total else None
        with mock.patch(
            "src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT",
            camps_root,
        ):
            save_manifest(campaign_id, manifest)
            save_checkpoint(
                campaign_id,
                {
                    "campaign_id": campaign_id,
                    "planned_trading_dates": planned,
                    "completed_dates": {planned[i]: f"run_{i}" for i in range(days_completed)},
                    "run_ids": [f"run_{i}" for i in range(days_completed)],
                    "accounts": None,
                },
            )

    def test_completed_campaign_not_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            camps = Path(tmp) / "campaigns"
            cid = "month_done"
            self._seed_campaign(
                camps,
                cid,
                status="month_completed",
                needs_resume=False,
                days_completed=5,
                days_total=5,
            )
            with mock.patch(
                "src.trading.competition.replay.campaign_select.CAMPAIGNS_ROOT",
                camps,
            ):
                with mock.patch(
                    "src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT",
                    camps,
                ):
                    with mock.patch(
                        "src.trading.competition.replay.campaign_select._load_firestore_campaigns",
                        return_value={},
                    ):
                        reason = resumability_exclusion_reason(load_manifest(cid))
            self.assertIn("terminal_status", reason or "")

    def test_checkpoint_campaign_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            camps = Path(tmp) / "campaigns"
            cid = "month_chk"
            self._seed_campaign(
                camps,
                cid,
                status=bc.STATUS_CHECKPOINT_WAITING,
                needs_resume=True,
                days_completed=2,
                days_total=5,
            )
            with mock.patch(
                "src.trading.competition.replay.campaign_select.CAMPAIGNS_ROOT",
                camps,
            ):
                with mock.patch(
                    "src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT",
                    camps,
                ):
                    with mock.patch(
                        "src.trading.competition.replay.campaign_select._load_firestore_campaigns",
                        return_value={},
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.campaign_select.DOCS_CAMPAIGNS_ROOT",
                            Path(tmp) / "docs",
                        ):
                            rows = list_auto_resumable_campaigns()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["campaign_id"], cid)


class CampaignBudgetCheckpointIntegrationTest(unittest.TestCase):
    def test_campaign_returns_budget_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            camps = Path(tmp) / "campaigns"
            cid = "month_test_budget"
            planned = ["20260102", "20260105", "20260106"]
            manifest = init_campaign_manifest(
                campaign_id=cid,
                replay_type="month",
                planned_dates=planned,
                chunk_size=1,
                period_start=planned[0],
                period_end=planned[-1],
            )
            with mock.patch(
                "src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT",
                camps,
            ):
                save_manifest(cid, manifest)
                save_checkpoint(
                    cid,
                    {
                        "campaign_id": cid,
                        "planned_trading_dates": planned,
                        "completed_dates": {},
                        "run_ids": [],
                        "accounts": None,
                    },
                )

            day_budget = {
                "ok": False,
                "error": "kis_request_budget_reached",
                "batch_status": "checkpoint_waiting_resume",
            }

            with mock.patch(
                "src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT",
                camps,
            ):
                with mock.patch(
                    "src.trading.competition.replay.campaign.camp_dir",
                    lambda c: camps / c,
                ):
                    with mock.patch(
                        "src.trading.competition.replay.campaign.ensure_campaign_for_resume",
                        return_value=(True, load_manifest(cid), None),
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.campaign.run_replay_single_day",
                            return_value=day_budget,
                        ):
                            with mock.patch(
                                "src.trading.competition.replay.campaign.sync_replay_campaign",
                                return_value={"ok": True},
                            ):
                                with mock.patch(
                                    "src.trading.competition.replay.campaign.is_campaign_ended",
                                    return_value=False,
                                ):
                                    from src.trading.competition.replay.campaign import (
                                        run_replay_campaign,
                                    )

                                    krl.reset_kis_rate_limit_state()
                                    result = run_replay_campaign(
                                        "month",
                                        planned[0],
                                        planned[-1],
                                        resume_existing_campaign=True,
                                        campaign_id=cid,
                                        chunk_size_trading_days=1,
                                        send_slack_reports=False,
                                    )

            self.assertTrue(result.get("ok"))
            self.assertTrue(result.get("needs_resume"))
            self.assertEqual(result.get("competition_status"), bc.STATUS_CHECKPOINT_WAITING)
            self.assertEqual(result.get("resume_reason"), bc.RESUME_REASON_BUDGET)


if __name__ == "__main__":
    unittest.main()
