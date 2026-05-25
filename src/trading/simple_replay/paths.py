"""Paths for SIMPLE_REPLAY storage (separate from advanced competition/replay)."""

from __future__ import annotations

from pathlib import Path

from src.trading.competition.storage.base import ROOT

SIMPLE_REPLAY_DATA_ROOT = ROOT / "data" / "simple_replay"
SIMPLE_REPLAY_RUNS_DIR = SIMPLE_REPLAY_DATA_ROOT / "runs"
SIMPLE_REPLAY_PAGES_ROOT = ROOT / "docs" / "simple-replay-data"


def run_dir(run_id: str) -> Path:
    return SIMPLE_REPLAY_RUNS_DIR / run_id


def ensure_dirs() -> None:
    SIMPLE_REPLAY_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SIMPLE_REPLAY_PAGES_ROOT.mkdir(parents=True, exist_ok=True)
