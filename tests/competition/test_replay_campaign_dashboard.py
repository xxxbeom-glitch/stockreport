# -*- coding: utf-8 -*-
"""Campaign-level REPLAY dashboard payload and Pages publish."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.trading.competition.dashboard import replay_payload as rp
from src.trading.competition.replay import pages_publish as pp
from src.trading.competition.replay import campaign_resume as cr
from src.trading.competition import runtime


class ReplayCampaignDashboardTests(unittest.TestCase):
    def test_build_campaign_dashboard_aggregates_timeline_and_trades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cid = "month_20260102_20260130_test01"
            planned = ["20260102", "20260103"]
            completed = {"20260102": "replay_20260102_a", "20260103": "replay_20260103_b"}

            patches = [
                mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "replay" / "campaigns"),
                mock.patch.object(cr, "COMPETITION_ROOT", root),
                mock.patch.object(rp, "REPLAY_ROOT", root / "replay"),
                mock.patch.object(rp, "COMPETITION_ROOT", root),
                mock.patch.object(runtime, "COMPETITION_ROOT", root),
            ]
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                for d, rid in completed.items():
                    run_dir = root / "replay" / rid
                    run_dir.mkdir(parents=True)
                    total = 510000 if d == "20260102" else 520000
                    (run_dir / "manifest.json").write_text(
                        json.dumps(
                            {
                                "replay_run_id": rid,
                                "campaign_id": cid,
                                "trading_date": d,
                                "accounts": {
                                    "A": {"cash_krw": total, "total_assets_krw": total, "positions": []},
                                    "B": {"cash_krw": 500000, "total_assets_krw": 500000, "positions": []},
                                    "C": {"cash_krw": 500000, "total_assets_krw": 500000, "positions": []},
                                    "D": {"cash_krw": 500000, "total_assets_krw": 500000, "positions": []},
                                },
                            }
                        ),
                        encoding="utf-8",
                    )
                    (run_dir / "trades.jsonl").write_text(
                        json.dumps(
                            {
                                "team_id": "A",
                                "ticker": "005930",
                                "name": "TestCo",
                                "side": "buy",
                                "fill_price_krw": 70000,
                                "quantity": 1,
                                "fill_date": d,
                            },
                            ensure_ascii=False,
                        )
                        + "\n",
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
                manifest["completed_dates"] = completed
                manifest["run_ids"] = list(completed.values())
                manifest["days_completed"] = 2
                manifest["days_total"] = 2
                cr.save_manifest(cid, manifest)
                cr.save_checkpoint(
                    cid,
                    {
                        "campaign_id": cid,
                        "planned_trading_dates": planned,
                        "completed_dates": completed,
                        "run_ids": list(completed.values()),
                        "accounts": json.loads((root / "replay" / "replay_20260103_b" / "manifest.json").read_text())[
                            "accounts"
                        ],
                        "last_completed_date": "20260103",
                    },
                )

                payload = rp.build_campaign_dashboard_payload(cid, prefer_local=True)
                self.assertEqual(payload["campaignId"], cid)
                self.assertEqual(payload["operatingDays"], 2)
                self.assertEqual(len(payload["timeline"]["labels"]), 3)
                self.assertEqual(len(payload["tradeHistory"]["agent1"]), 2)

    def test_publish_campaign_full_writes_campaign_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pub_root = root / "docs"
            cid = "month_20260102_20260130_pub01"
            rid = "replay_20260102_pub"
            run_dir = root / "replay" / rid
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "replay_run_id": rid,
                        "campaign_id": cid,
                        "trading_date": "20260102",
                        "accounts": {
                            "A": {"cash_krw": 500000, "total_assets_krw": 500000, "positions": []},
                            "B": {"cash_krw": 500000, "total_assets_krw": 500000, "positions": []},
                            "C": {"cash_krw": 500000, "total_assets_krw": 500000, "positions": []},
                            "D": {"cash_krw": 500000, "total_assets_krw": 500000, "positions": []},
                        },
                    }
                ),
                encoding="utf-8",
            )
            camp = root / "replay" / "campaigns" / cid
            camp.mkdir(parents=True)
            (camp / "manifest.json").write_text(
                json.dumps(
                    {
                        "campaign_id": cid,
                        "replay_type": "month",
                        "planned_trading_dates": ["20260102"],
                        "completed_dates": {"20260102": rid},
                        "run_ids": [rid],
                        "days_completed": 1,
                        "days_total": 1,
                        "accounts": json.loads((run_dir / "manifest.json").read_text())["accounts"],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(pp, "REPLAY_DATA_ROOT", pub_root / "replay-data"):
                with mock.patch.object(pp, "LOCAL_REPLAY_ROOT", root / "replay"):
                    with mock.patch.object(cr, "CAMPAIGNS_ROOT", root / "replay" / "campaigns"):
                        with mock.patch.object(cr, "COMPETITION_ROOT", root):
                            with mock.patch.object(rp, "REPLAY_ROOT", root / "replay"):
                                with mock.patch.object(rp, "COMPETITION_ROOT", root):
                                    with mock.patch.object(runtime, "COMPETITION_ROOT", root):
                                        result = pp.publish_campaign_full(cid)
            self.assertTrue(result.get("ok"))
            dash = pub_root / "replay-data" / "campaigns" / cid / "dashboard.json"
            run_dash = pub_root / "replay-data" / "runs" / rid / "dashboard.json"
            self.assertTrue(dash.is_file())
            self.assertTrue(run_dash.is_file())


if __name__ == "__main__":
    unittest.main()
