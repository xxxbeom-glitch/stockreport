# -*- coding: utf-8 -*-
"""Phase 1 tests — competition account bootstrap and isolation."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.bootstrap import bootstrap_competition, verify_isolation
from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS
from src.trading.competition.storage.accounts import load_all_accounts
from src.trading.competition.storage.config_store import is_initialized, load_config


class CompetitionBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._data_dir = Path(self._tmpdir) / "data" / "competition"
        self._data_dir.mkdir(parents=True)

        self._patches = [
            patch(
                "src.trading.competition.storage.base.LOCAL_DIR",
                self._data_dir,
            ),
            patch(
                "src.trading.competition.storage.base.ensure_local_dir",
                return_value=self._data_dir,
            ),
            patch(
                "src.trading.competition.storage.accounts.ACCOUNTS_PATH",
                self._data_dir / "accounts.json",
            ),
            patch(
                "src.trading.competition.storage.accounts.ensure_local_dir",
                return_value=self._data_dir,
            ),
            patch(
                "src.trading.competition.storage.positions.POSITIONS_PATH",
                self._data_dir / "positions.json",
            ),
            patch(
                "src.trading.competition.storage.positions.ensure_local_dir",
                return_value=self._data_dir,
            ),
            patch(
                "src.trading.competition.storage.config_store.CONFIG_PATH",
                self._data_dir / "config.json",
            ),
            patch(
                "src.trading.competition.storage.config_store.ensure_local_dir",
                return_value=self._data_dir,
            ),
            patch(
                "src.trading.competition.storage.base.firestore_client",
                return_value=(None, {"ok": False, "error": "test:no_firestore"}),
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_initial_bootstrap_creates_four_teams(self) -> None:
        result = bootstrap_competition()
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "initialized")
        self.assertEqual(set(result["created_teams"]), set(TEAM_IDS))

        accounts = load_all_accounts()
        self.assertEqual(len(accounts), 4)
        for tid in TEAM_IDS:
            acc = accounts[tid]
            self.assertEqual(acc.cash_krw, INITIAL_CASH_KRW)
            self.assertEqual(acc.total_assets_krw, INITIAL_CASH_KRW)
            self.assertEqual(acc.status, "active")

    def test_idempotent_second_run_does_not_reset(self) -> None:
        bootstrap_competition()
        accounts_first = load_all_accounts()
        bootstrap_competition()
        accounts_second = load_all_accounts()
        self.assertEqual(accounts_first, accounts_second)
        self.assertTrue(is_initialized())

    def test_force_reset_rejected(self) -> None:
        bootstrap_competition()
        result = bootstrap_competition(force=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "force_reset_not_implemented")

    def test_isolation_metadata(self) -> None:
        info = verify_isolation()
        self.assertTrue(info["uses_separate_local_dir"])
        self.assertEqual(info["collection_prefix"], "competition_")


if __name__ == "__main__":
    unittest.main()
