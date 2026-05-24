"""Execution mode routing — LIVE vs REPLAY vs AUDIT."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

ExecutionMode = Literal["live", "replay_smoke", "replay_audit"]

ROOT = Path(__file__).resolve().parents[3]
COMPETITION_ROOT = ROOT / "data" / "competition"


def get_execution_mode() -> ExecutionMode:
    raw = (os.getenv("COMPETITION_EXECUTION_MODE") or "live").strip().lower()
    if raw in ("replay_smoke", "replay_audit", "live"):
        return raw  # type: ignore[return-value]
    return "live"


def is_replay_mode() -> bool:
    return get_execution_mode() in ("replay_smoke", "replay_audit")


def is_live_mode() -> bool:
    return get_execution_mode() == "live"


def live_data_dir() -> Path:
    """LIVE mirror directory (never used during replay writes)."""
    override = os.getenv("COMPETITION_LIVE_DATA_DIR", "").strip()
    if override:
        return Path(override)
    live_sub = COMPETITION_ROOT / "live"
    if live_sub.is_dir() or not COMPETITION_ROOT.is_dir():
        return live_sub
    return COMPETITION_ROOT


def replay_run_dir(replay_run_id: str) -> Path:
    return COMPETITION_ROOT / "replay" / replay_run_id


def audit_run_dir(audit_run_id: str) -> Path:
    return COMPETITION_ROOT / "audit" / audit_run_id


def assert_live_session_allowed() -> None:
    """Block accidental live session while replay validation is in progress."""
    if is_replay_mode():
        raise RuntimeError(
            f"Live session blocked: COMPETITION_EXECUTION_MODE={get_execution_mode()}"
        )
    if os.getenv("COMPETITION_ALLOW_LIVE_SESSION", "").lower() not in ("1", "true", "yes"):
        if os.getenv("COMPETITION_LIVE_SCHEDULE_DISABLED", "1").lower() in ("1", "true", "yes"):
            raise RuntimeError(
                "LIVE automatic session is disabled until replay validation passes. "
                "Set COMPETITION_ALLOW_LIVE_SESSION=1 only after audit approval."
            )


def replay_meta(
    *,
    replay_run_id: str,
    as_of_from: str,
    as_of_to: str,
    mode: ExecutionMode | None = None,
) -> dict:
    m = mode or get_execution_mode()
    return {
        "execution_mode": m,
        "replay_run_id": replay_run_id,
        "as_of_from": as_of_from,
        "as_of_to": as_of_to,
        "reset_required_before_live": False,
        "affects_live_account": False,
    }
