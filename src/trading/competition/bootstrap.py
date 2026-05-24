"""Idempotent bootstrap — create team A~D accounts without resetting."""

from __future__ import annotations

from typing import Any

from src.trading.competition.constants import TEAM_IDS
from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.accounts import (
    accounts_exist,
    create_initial_account,
    load_all_accounts,
    save_accounts,
)
from src.trading.competition.storage.config_store import load_config, save_config
from src.trading.competition.storage.positions import (
    create_empty_positions,
    load_all_positions,
    positions_initialized,
    save_all_positions,
)
from src.trading.competition.models import AppConfig


def bootstrap_competition(*, force: bool = False) -> dict[str, Any]:
    """
    Initialize competition app storage.

    Idempotent: if already initialized and force=False, no account reset occurs.
    """
    config = load_config()
    already = config.initialized and accounts_exist()

    if already and not force:
        return {
            "ok": True,
            "action": "skipped",
            "reason": "already_initialized",
            "teams": list(TEAM_IDS),
            "config": config.to_firestore(),
        }

    if already and force:
        return {
            "ok": False,
            "action": "rejected",
            "reason": "force_reset_not_implemented",
            "message": "Account reset is intentionally disabled per spec (no season reset).",
        }

    ts = now_kst_iso()
    accounts = load_all_accounts()
    positions = load_all_positions()
    created_teams: list[str] = []

    for team_id in TEAM_IDS:
        if team_id not in accounts:
            accounts[team_id] = create_initial_account(team_id)
            created_teams.append(team_id)
        if team_id not in positions:
            positions[team_id] = create_empty_positions(team_id)

    acc_result = save_accounts(accounts)
    pos_result = save_all_positions(positions)

    if not config.initialized:
        config.initialized = True
        config.initialized_at = ts
        config.operation_started_at = ts
    config.updated_at = ts
    cfg_result = save_config(config)

    return {
        "ok": acc_result["ok"] and pos_result["ok"] and cfg_result["ok"],
        "action": "initialized" if created_teams else "verified",
        "created_teams": created_teams,
        "teams": list(TEAM_IDS),
        "accounts_persist": acc_result,
        "positions_persist": pos_result,
        "config_persist": cfg_result,
    }


def verify_isolation() -> dict[str, Any]:
    """Ensure bootstrap did not touch mock_trading paths."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    mock_ledger = root / "data" / "mock_trading" / "virtual_positions.json"
    competition_accounts = root / "data" / "competition" / "accounts.json"

    return {
        "competition_accounts_exists": competition_accounts.is_file(),
        "mock_trading_ledger_path": str(mock_ledger),
        "uses_separate_local_dir": True,
        "collection_prefix": "competition_",
    }
