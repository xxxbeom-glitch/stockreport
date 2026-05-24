"""REPLAY market/decision input validity — block ok:true when data is unusable."""

from __future__ import annotations

from typing import Any

from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS


def _priced_universe_count(snapshot: dict[str, Any]) -> int:
    n = 0
    for row in snapshot.get("eligible_universe") or []:
        if int(row.get("current_price_krw") or 0) > 0:
            n += 1
    return n


def _scout_candidate_count(snapshot: dict[str, Any]) -> int:
    total = 0
    for tid in TEAM_IDS:
        total += len((snapshot.get("team_scouts") or {}).get(tid) or [])
    return total


def validate_snapshot_for_replay(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Fail fast when OHLCV/universe/scout inputs are missing."""
    if not snapshot.get("ok"):
        return {
            "valid": False,
            "data_status": "data_invalid",
            "reason": str(snapshot.get("error") or "snapshot_failed"),
            "universe_count": 0,
            "priced_universe_count": 0,
            "scout_candidate_count": 0,
        }

    enrich = snapshot.get("enrich") or {}
    if enrich and enrich.get("ok") is False:
        return {
            "valid": False,
            "data_status": "data_invalid",
            "reason": str(enrich.get("error") or "universe_enrich_failed"),
            "universe_count": int(snapshot.get("universe_count") or 0),
            "priced_universe_count": _priced_universe_count(snapshot),
            "scout_candidate_count": _scout_candidate_count(snapshot),
            "enrich": enrich,
        }

    universe_count = int(snapshot.get("universe_count") or len(snapshot.get("eligible_universe") or []))
    priced = _priced_universe_count(snapshot)
    scouts = _scout_candidate_count(snapshot)

    if universe_count <= 0:
        return {
            "valid": False,
            "data_status": "data_invalid",
            "reason": "eligible_universe_empty",
            "universe_count": universe_count,
            "priced_universe_count": priced,
            "scout_candidate_count": scouts,
        }
    if priced <= 0:
        return {
            "valid": False,
            "data_status": "data_invalid",
            "reason": "no_priced_universe_rows",
            "universe_count": universe_count,
            "priced_universe_count": priced,
            "scout_candidate_count": scouts,
        }
    if scouts <= 0:
        return {
            "valid": False,
            "data_status": "data_invalid",
            "reason": "no_scout_candidates_for_any_team",
            "universe_count": universe_count,
            "priced_universe_count": priced,
            "scout_candidate_count": scouts,
        }

    return {
        "valid": True,
        "data_status": "data_ready",
        "reason": None,
        "universe_count": universe_count,
        "priced_universe_count": priced,
        "scout_candidate_count": scouts,
    }


def validate_replay_run_outcome(
    snapshot: dict[str, Any],
    *,
    accounts: dict[str, dict[str, Any]],
    team_results: dict[str, Any],
) -> dict[str, Any]:
    """
  After decisions: distinguish valid all-HOLD vs invalid flat seed with no trading activity.
  """
    base = validate_snapshot_for_replay(snapshot)
    if not base["valid"]:
        return base

    all_seed = True
    any_position = False
    any_non_hold = False
    statuses: list[str] = []

    for tid in TEAM_IDS:
        acc = accounts.get(tid) or {}
        cash = int(acc.get("cash_krw") or 0)
        total = int(acc.get("total_assets_krw") or cash)
        positions = acc.get("positions") or []
        if positions:
            any_position = True
        if cash != INITIAL_CASH_KRW or total != INITIAL_CASH_KRW:
            all_seed = False
        tm = team_results.get(tid) or {}
        action = str(tm.get("action") or "").upper()
        status = str(tm.get("status") or "")
        statuses.append(status)
        if action in ("BUY", "ADD_BUY", "SELL"):
            any_non_hold = True
        if status.startswith("filled") or status == "filled_next_session":
            any_non_hold = True

    if any_position or any_non_hold or not all_seed:
        return {
            **base,
            "valid": True,
            "data_status": "trade_activity",
            "all_hold": False,
            "team_statuses": statuses,
        }

    return {
        **base,
        "valid": True,
        "data_status": "all_hold",
        "all_hold": True,
        "reason": "all_teams_no_order_at_seed_cash",
        "team_statuses": statuses,
    }


def merge_validity_into_manifest(manifest: dict[str, Any], validity: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(manifest)
    manifest["data_validity"] = validity
    manifest["data_status"] = validity.get("data_status")
    if not validity.get("valid"):
        manifest["ok"] = False
        manifest["error"] = manifest.get("error") or validity.get("reason") or "data_invalid"
    return manifest
