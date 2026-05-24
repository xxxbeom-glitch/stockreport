"""CI guard: smoke_1day import chain must resolve on a clean checkout."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ReplaySmokeImportTests(unittest.TestCase):
    def test_historical_seed_module_on_path(self) -> None:
        mod = importlib.import_module("src.trading.competition.ops.historical_seed")
        self.assertTrue(callable(mod.enrich_universe_historical))
        self.assertTrue(callable(mod.scout_teams_historical))

    def test_snapshot_builder_import_chain(self) -> None:
        sb = importlib.import_module("src.trading.competition.replay.snapshot_builder")
        self.assertTrue(callable(sb.build_close_snapshot))
        self.assertIn(
            "historical_seed",
            sb.enrich_universe_historical.__module__,
        )

    def test_run_competition_replay_entry_imports(self) -> None:
        importlib.import_module("src.trading.competition.replay.campaign")
        importlib.import_module("src.trading.competition.replay.runner")
        runner = importlib.import_module("scripts.run_competition_replay")
        self.assertTrue(callable(runner.main))


if __name__ == "__main__":
    unittest.main()
