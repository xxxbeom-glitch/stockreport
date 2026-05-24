# -*- coding: utf-8 -*-
"""Auto-select resumable REPLAY campaign for Actions."""

from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src.trading.competition.replay import campaign_select as cs
from src.trading.competition.replay.campaign_resume import CAMPAIGNS_ROOT, save_manifest


class ReplayCampaignSelectTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = CAMPAIGNS_ROOT.parent / "_test_select_campaigns"
        self._tmp.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        import shutil

        if self._tmp.is_dir():
            shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_manifest(self, cid: str, manifest: dict) -> None:
        with patch("src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT", self._tmp):
            save_manifest(cid, manifest)

    @contextmanager
    def _patches(self, docs_root: Path | None = None):
        docs = docs_root or (self._tmp / "docs_empty")
        with (
            patch("src.trading.competition.replay.campaign_resume.CAMPAIGNS_ROOT", self._tmp),
            patch.object(cs, "CAMPAIGNS_ROOT", self._tmp),
            patch.object(cs, "DOCS_CAMPAIGNS_ROOT", docs),
        ):
            yield

    def test_excludes_duplicate_meta(self) -> None:
        dup_meta = {
            "campaignId": "month_20260102_20260130_a6b1b1",
            "doNotResume": True,
            "campaignKind": "duplicate_restart",
            "canonicalCampaignId": "month_20260102_20260130_1b51cb",
        }
        docs = self._tmp / "docs"
        with self._patches(docs):
            dup_dir = docs / "month_20260102_20260130_a6b1b1"
            dup_dir.mkdir(parents=True)
            (dup_dir / "meta.json").write_text(json.dumps(dup_meta), encoding="utf-8")
            rows = cs.list_auto_resumable_campaigns()
        self.assertEqual(rows, [])

    def test_excludes_all_known_duplicates(self) -> None:
        docs = self._tmp / "docs"
        dup_ids = (
            "month_20260102_20260130_a6b1b1",
            "month_20260102_20260130_d95c8a",
            "month_20260102_20260130_615f0d",
        )
        with self._patches(docs):
            for cid in dup_ids:
                d = docs / cid
                d.mkdir(parents=True)
                (d / "meta.json").write_text(
                    json.dumps(
                        {
                            "campaignId": cid,
                            "doNotResume": True,
                            "campaignKind": "duplicate_restart",
                            "canonicalCampaignId": "month_20260102_20260130_1b51cb",
                        }
                    ),
                    encoding="utf-8",
                )
            rows = cs.list_auto_resumable_campaigns()
        self.assertEqual(rows, [])

    def test_selects_single_canonical(self) -> None:
        manifest = {
            "campaign_id": "month_20260102_20260130_1b51cb",
            "replay_type": "month",
            "period_start": "20260102",
            "period_end": "20260130",
            "planned_trading_dates": ["20260102", "20260105", "20260109"],
            "completed_dates": {"20260102": "r1", "20260105": "r2"},
            "needs_resume": True,
            "next_trading_date": "20260109",
            "days_completed": 2,
            "days_total": 3,
            "competition_status": "active",
            "ok": False,
            "error": "data_invalid",
        }
        with self._patches():
            self._write_manifest("month_20260102_20260130_1b51cb", manifest)
            result = cs.select_unique_resumable_campaign()
        self.assertTrue(result["ok"])
        self.assertEqual(result["campaign_id"], "month_20260102_20260130_1b51cb")
        self.assertEqual(result["next_trading_date"], "20260109")

    def test_multiple_candidates_fails(self) -> None:
        base = {
            "replay_type": "month",
            "planned_trading_dates": ["20260102", "20260105"],
            "needs_resume": True,
            "next_trading_date": "20260105",
            "days_completed": 1,
            "days_total": 2,
            "competition_status": "active",
        }
        with self._patches():
            self._write_manifest(
                "month_20260102_20260130_aaa111",
                {**base, "campaign_id": "month_20260102_20260130_aaa111"},
            )
            self._write_manifest(
                "month_20260102_20260130_bbb222",
                {**base, "campaign_id": "month_20260102_20260130_bbb222"},
            )
            result = cs.select_unique_resumable_campaign()
        self.assertFalse(result["ok"])
        self.assertIn("Multiple resumable campaigns", result["error"])

    def test_zero_candidates_fails(self) -> None:
        with self._patches():
            result = cs.select_unique_resumable_campaign()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "No resumable campaign found")


if __name__ == "__main__":
    unittest.main()
