# -*- coding: utf-8
"""Readiness gate tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.ops.readiness import RECOMMENDED_MODELS, check_live_readiness


class ReadinessTest(unittest.TestCase):
    def test_recommended_models_use_flash_first(self) -> None:
        self.assertEqual(RECOMMENDED_MODELS["COMPETITION_A_MAIN_MODEL"], "deepseek-v4-flash")
        self.assertEqual(RECOMMENDED_MODELS["COMPETITION_D_VALIDATOR_MODEL"], "deepseek-v4-pro")

    @patch("src.trading.competition.ops.readiness.provider_available", return_value=True)
    @patch("src.trading.competition.ops.readiness.resolve_model", return_value=("deepseek", "deepseek-v4-flash"))
    @patch("src.trading.competition.storage.base.firestore_client")
    def test_firebase_missing_blocks_live_ops(self, mock_fs, *_mocks) -> None:
        mock_fs.return_value = (None, {"ok": False, "error": "firebase unavailable"})
        report = check_live_readiness(allow_local_mirror=False)
        self.assertFalse(report["ready_for_live_ops"])
        self.assertTrue(any("Firebase" in b for b in report["blockers"]))

    @patch("src.trading.competition.ops.readiness.provider_available", return_value=True)
    @patch("src.trading.competition.ops.readiness.resolve_model", return_value=("deepseek", "deepseek-v4-flash"))
    @patch("src.trading.competition.storage.base.firestore_client")
    def test_firebase_missing_allowed_for_local_mirror_flag(self, mock_fs, *_mocks) -> None:
        mock_fs.return_value = (None, {"ok": False, "error": "firebase unavailable"})
        report = check_live_readiness(allow_local_mirror=True)
        self.assertFalse(any("Firebase" in b for b in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
