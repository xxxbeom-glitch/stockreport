"""Resumable REPLAY campaign chunk / checkpoint tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.trading.competition.replay import campaign as campaign_mod
from src.trading.competition.replay import campaign_resume as cr
from src.trading.competition.replay import finalize as finalize_mod


class CampaignResumeHelpersTests(unittest.TestCase):
    def test_progress_label_month(self) -> None:
        label = cr.progress_label("month", "20260102", 10, 21)
        self.assertIn("1월", label)
        self.assertIn("10 / 21", label)

    def test_terminal_status(self) -> None:
        self.assertTrue(cr.is_terminal_status("month_completed"))
        self.assertTrue(cr.is_terminal_status("ended"))
        self.assertFalse(cr.is_terminal_status("active"))

    def test_mark_day_completed_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cid = "month_20260102_20260130_abc123"
            camp = root / "campaigns" / cid
            camp.mkdir(parents=True)
            ck = {
                "campaign_id": cid,
                "planned_trading_dates": ["20260102", "20260103"],
                "completed_dates": {},
                "run_ids": [],
            }
            with mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "campaigns"):
                with mock.patch.object(cr, "COMPETITION_ROOT", root):
                    cr.save_checkpoint(cid, ck)
                    ck2 = cr.mark_day_completed(
                        cid,
                        trading_date="20260102",
                        replay_run_id="replay_20260102_aaa",
                        accounts={"team_a": {"cash_krw": 1}},
                        checkpoint=ck,
                    )
                    self.assertEqual(ck2["completed_dates"]["20260102"], "replay_20260102_aaa")
                    ck3 = cr.mark_day_completed(
                        cid,
                        trading_date="20260102",
                        replay_run_id="replay_20260102_aaa",
                        accounts={"team_a": {"cash_krw": 1}},
                        checkpoint=ck2,
                    )
                    self.assertEqual(len(ck3["run_ids"]), 1)


class CampaignChunkRunTests(unittest.TestCase):
    def test_new_campaign_processes_only_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = ["20260102", "20260103", "20260106", "20260107", "20260108", "20260109"]
            call_dates: list[str] = []

            def fake_day(trading_date: str, **kwargs: object) -> dict[str, object]:
                call_dates.append(trading_date)
                return {
                    "ok": True,
                    "replay_run_id": f"replay_{trading_date}_test",
                    "accounts": {"team_a": {"cash_krw": 500000, "positions": [], "total_assets_krw": 500000}},
                    "leakage_summary": "PASS",
                }

            patches = [
                mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "campaigns"),
                mock.patch.object(cr, "COMPETITION_ROOT", root),
                mock.patch.object(finalize_mod, "CAMPAIGNS_ROOT", root / "campaigns"),
            ]
            with patches[0], patches[1], patches[2]:
                with mock.patch(
                        "src.trading.competition.replay.campaign.is_campaign_ended",
                        return_value=False,
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.campaign.resolve_replay_dates_with_meta",
                            return_value=(dates, {"ok": True}),
                        ):
                            with mock.patch(
                                "src.trading.competition.replay.campaign.run_replay_single_day",
                                side_effect=fake_day,
                            ):
                                with mock.patch(
                                    "src.trading.competition.replay.campaign.build_replay_weekly_reports",
                                    return_value=[],
                                ):
                                    with mock.patch(
                                        "src.trading.competition.replay.campaign.build_replay_monthly_reports",
                                        return_value=[],
                                    ):
                                        with mock.patch(
                                            "src.trading.competition.replay.campaign.save_campaign_reports",
                                            return_value={},
                                        ):
                                            with mock.patch(
                                                "src.trading.competition.replay.campaign.sync_replay_campaign",
                                                return_value={},
                                            ):
                                                r1 = campaign_mod.run_replay_campaign(
                                                    "month",
                                                    "20260102",
                                                    None,
                                                    send_slack_reports=False,
                                                    chunk_size_trading_days=2,
                                                )
            self.assertTrue(r1.get("ok"))
            self.assertEqual(len(r1.get("chunk_processed_dates") or []), 2)
            self.assertEqual(call_dates, ["20260102", "20260103"])
            self.assertTrue(r1.get("needs_resume"))
            cid = r1["campaign_id"]

            call_dates.clear()
            patches = [
                mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "campaigns"),
                mock.patch.object(cr, "COMPETITION_ROOT", root),
                mock.patch.object(finalize_mod, "CAMPAIGNS_ROOT", root / "campaigns"),
            ]
            with patches[0], patches[1], patches[2]:
                with mock.patch(
                        "src.trading.competition.replay.campaign.is_campaign_ended",
                        return_value=False,
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.campaign.run_replay_single_day",
                            side_effect=fake_day,
                        ):
                            with mock.patch(
                                "src.trading.competition.replay.campaign.build_replay_weekly_reports",
                                return_value=[],
                            ):
                                with mock.patch(
                                    "src.trading.competition.replay.campaign.build_replay_monthly_reports",
                                    return_value=[],
                                ):
                                    with mock.patch(
                                        "src.trading.competition.replay.campaign.save_campaign_reports",
                                        return_value={},
                                    ):
                                        with mock.patch(
                                            "src.trading.competition.replay.campaign.sync_replay_campaign",
                                            return_value={},
                                        ):
                                            r2 = campaign_mod.run_replay_campaign(
                                                "month",
                                                "20260102",
                                                None,
                                                send_slack_reports=False,
                                                resume_existing_campaign=True,
                                                campaign_id=cid,
                                                chunk_size_trading_days=2,
                                            )
            self.assertEqual(call_dates, ["20260106", "20260107"])
            self.assertEqual(len(r2.get("chunk_processed_dates") or []), 2)

            call_dates.clear()
            patches = [
                mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "campaigns"),
                mock.patch.object(cr, "COMPETITION_ROOT", root),
                mock.patch.object(finalize_mod, "CAMPAIGNS_ROOT", root / "campaigns"),
            ]
            with patches[0], patches[1], patches[2]:
                with mock.patch(
                        "src.trading.competition.replay.campaign.is_campaign_ended",
                        return_value=False,
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.campaign.run_replay_single_day",
                            side_effect=fake_day,
                        ):
                            with mock.patch(
                                "src.trading.competition.replay.campaign.build_replay_weekly_reports",
                                return_value=[],
                            ):
                                with mock.patch(
                                    "src.trading.competition.replay.campaign.build_replay_monthly_reports",
                                    return_value=[{"month_key": "m202601"}],
                                ):
                                    with mock.patch(
                                        "src.trading.competition.replay.campaign.save_campaign_reports",
                                        return_value={},
                                    ):
                                        with mock.patch(
                                            "src.trading.competition.replay.campaign.sync_replay_campaign",
                                            return_value={},
                                        ):
                                            r3 = campaign_mod.run_replay_campaign(
                                                "month",
                                                "20260102",
                                                None,
                                                send_slack_reports=False,
                                                resume_existing_campaign=True,
                                                campaign_id=cid,
                                                chunk_size_trading_days=5,
                                            )
            self.assertEqual(call_dates, ["20260108", "20260109"])
            self.assertEqual(r3.get("competition_status"), "month_completed")
            self.assertFalse(r3.get("needs_resume"))

    def test_resume_skips_completed_without_ai(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cid = "month_20260102_20260103_xyz"
            run_id = "replay_20260102_done"
            run_dir = root / "replay" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "replay_run_id": run_id,
                        "campaign_id": cid,
                        "trading_date": "20260102",
                        "accounts": {"team_a": {"cash_krw": 400000, "positions": [], "total_assets_krw": 400000}},
                    }
                ),
                encoding="utf-8",
            )
            camp = root / "campaigns" / cid
            camp.mkdir(parents=True)
            manifest = cr.init_campaign_manifest(
                campaign_id=cid,
                replay_type="month",
                planned_dates=["20260102", "20260103"],
                chunk_size=5,
                period_start="20260102",
                period_end="20260103",
            )
            patches = [
                mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "campaigns"),
                mock.patch.object(cr, "COMPETITION_ROOT", root),
                mock.patch.object(finalize_mod, "CAMPAIGNS_ROOT", root / "campaigns"),
            ]
            with patches[0], patches[1], patches[2]:
                cr.save_manifest(cid, manifest)
                cr.save_checkpoint(
                    cid,
                    {
                        "campaign_id": cid,
                        "planned_trading_dates": ["20260102", "20260103"],
                        "completed_dates": {"20260102": run_id},
                        "run_ids": [run_id],
                        "accounts": {
                            "team_a": {
                                "cash_krw": 400000,
                                "positions": [],
                                "total_assets_krw": 400000,
                            }
                        },
                    },
                )
                with mock.patch(
                        "src.trading.competition.replay.campaign.is_campaign_ended",
                        return_value=False,
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.campaign.run_replay_single_day",
                        ) as mock_run:
                            mock_run.return_value = {
                                "ok": True,
                                "replay_run_id": "replay_20260103_new",
                                "accounts": {"team_a": {"cash_krw": 300000, "positions": [], "total_assets_krw": 300000}},
                                "leakage_summary": "PASS",
                            }
                            with mock.patch(
                                "src.trading.competition.replay.campaign.build_replay_weekly_reports",
                                return_value=[],
                            ):
                                with mock.patch(
                                    "src.trading.competition.replay.campaign.build_replay_monthly_reports",
                                    return_value=[{"month_key": "m202601"}],
                                ):
                                    with mock.patch(
                                        "src.trading.competition.replay.campaign.save_campaign_reports",
                                        return_value={},
                                    ):
                                        with mock.patch(
                                            "src.trading.competition.replay.campaign.sync_replay_campaign",
                                            return_value={},
                                        ):
                                            r = campaign_mod.run_replay_campaign(
                                                "month",
                                                "20260102",
                                                None,
                                                send_slack_reports=False,
                                                resume_existing_campaign=True,
                                                campaign_id=cid,
                                            )
            mock_run.assert_called_once()
            self.assertEqual(mock_run.call_args[0][0], "20260103")

    def test_resume_must_not_create_new_campaign_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = ["20260102", "20260103", "20260106", "20260107", "20260108", "20260109"]
            patches = [
                mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "campaigns"),
                mock.patch.object(cr, "COMPETITION_ROOT", root),
                mock.patch.object(finalize_mod, "CAMPAIGNS_ROOT", root / "campaigns"),
            ]
            with patches[0], patches[1], patches[2]:
                with mock.patch(
                    "src.trading.competition.replay.campaign.is_campaign_ended",
                    return_value=False,
                ):
                    with mock.patch(
                        "src.trading.competition.replay.campaign.resolve_replay_dates_with_meta",
                        return_value=(dates, {"ok": True}),
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.campaign.ensure_campaign_for_resume",
                            return_value=(False, {}, "campaign_not_found_firestore"),
                        ):
                            r = campaign_mod.run_replay_campaign(
                                "month",
                                "20260102",
                                None,
                                send_slack_reports=False,
                                resume_existing_campaign=True,
                                campaign_id="month_20260102_20260130_1b51cb",
                            )
            self.assertFalse(r.get("ok"))
            self.assertEqual(r.get("error"), "campaign_not_found_firestore")
            self.assertTrue(r.get("resume_requested"))

    def test_resume_continues_from_day_six_after_five_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cid = "month_20260102_20260130_1b51cb"
            planned = [
                "20260102",
                "20260105",
                "20260106",
                "20260107",
                "20260108",
                "20260109",
                "20260112",
            ]
            completed_runs = {
                d: f"replay_{d}_done" for d in planned[:5]
            }
            for d, rid in completed_runs.items():
                run_dir = root / "replay" / rid
                run_dir.mkdir(parents=True)
                (run_dir / "manifest.json").write_text(
                    json.dumps(
                        {
                            "replay_run_id": rid,
                            "campaign_id": cid,
                            "trading_date": d,
                            "accounts": {
                                "A": {"cash_krw": 400000, "positions": [], "total_assets_krw": 400000}
                            },
                        }
                    ),
                    encoding="utf-8",
                )
            manifest = cr.init_campaign_manifest(
                campaign_id=cid,
                replay_type="month",
                planned_dates=planned,
                chunk_size=5,
                period_start="20260102",
                period_end="20260130",
            )
            manifest["days_completed"] = 5
            manifest["days_total"] = 21
            manifest["completed_trading_dates"] = list(planned[:5])
            manifest["completed_dates"] = completed_runs
            manifest["run_ids"] = list(completed_runs.values())
            manifest["next_trading_date"] = "20260109"
            manifest["needs_resume"] = True

            patches = [
                mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "campaigns"),
                mock.patch.object(cr, "COMPETITION_ROOT", root),
                mock.patch.object(finalize_mod, "CAMPAIGNS_ROOT", root / "campaigns"),
            ]
            call_dates: list[str] = []

            def fake_day(trading_date: str, **kwargs: object) -> dict[str, object]:
                call_dates.append(trading_date)
                return {
                    "ok": True,
                    "replay_run_id": f"replay_{trading_date}_new",
                    "accounts": {"A": {"cash_krw": 300000, "positions": [], "total_assets_krw": 300000}},
                    "leakage_summary": "PASS",
                }

            with patches[0], patches[1], patches[2]:
                cr.save_manifest(cid, manifest)
                cr.save_checkpoint(
                    cid,
                    {
                        "campaign_id": cid,
                        "planned_trading_dates": planned,
                        "completed_dates": completed_runs,
                        "run_ids": list(completed_runs.values()),
                        "accounts": {"A": {"cash_krw": 400000, "positions": [], "total_assets_krw": 400000}},
                    },
                )
                with mock.patch(
                    "src.trading.competition.replay.campaign.is_campaign_ended",
                    return_value=False,
                ):
                    with mock.patch(
                        "src.trading.competition.replay.campaign.run_replay_single_day",
                        side_effect=fake_day,
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.campaign.build_replay_weekly_reports",
                            return_value=[],
                        ):
                            with mock.patch(
                                "src.trading.competition.replay.campaign.build_replay_monthly_reports",
                                return_value=[],
                            ):
                                with mock.patch(
                                    "src.trading.competition.replay.campaign.save_campaign_reports",
                                    return_value={},
                                ):
                                    with mock.patch(
                                        "src.trading.competition.replay.campaign.sync_replay_campaign",
                                        return_value={},
                                    ):
                                        r = campaign_mod.run_replay_campaign(
                                            "month",
                                            "20260102",
                                            None,
                                            send_slack_reports=False,
                                            resume_existing_campaign=True,
                                            campaign_id=cid,
                                            chunk_size_trading_days=5,
                                        )
            self.assertEqual(r.get("campaign_id"), cid)
            self.assertEqual(call_dates, ["20260109", "20260112"])
            self.assertNotIn("20260102", call_dates)


if __name__ == "__main__":
    unittest.main()
