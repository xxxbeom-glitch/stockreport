"""Team positions storage."""

from __future__ import annotations

from typing import Any

from src.trading.competition.constants import COLLECTION_POSITIONS, TEAM_IDS
from src.trading.competition.models import TeamPositions, now_kst_iso
from src.trading.competition.storage.base import (
    ensure_local_dir,
    firestore_client,
    load_json_file,
    persist_result,
    save_json_file,
)

POSITIONS_PATH = ensure_local_dir() / "positions.json"


def _default_positions_doc() -> dict[str, Any]:
    return {"teams": {}, "updated_at": ""}


def load_all_positions() -> dict[str, TeamPositions]:
    raw = load_json_file(POSITIONS_PATH, _default_positions_doc())
    teams = raw.get("teams") or {}
    return {tid: TeamPositions.from_dict({**data, "team_id": tid}) for tid, data in teams.items()}


def load_team_positions(team_id: str) -> TeamPositions:
    all_pos = load_all_positions()
    if team_id in all_pos:
        return all_pos[team_id]
    return TeamPositions(team_id=team_id)  # type: ignore[arg-type]


def save_all_positions(positions: dict[str, TeamPositions]) -> dict[str, Any]:
    payload = {
        "teams": {tid: tp.to_firestore() for tid, tp in positions.items()},
        "updated_at": now_kst_iso(),
    }
    save_json_file(POSITIONS_PATH, payload)

    client, status = firestore_client()
    firestore_ok = False
    firestore_error = status.get("error", "")
    if client:
        try:
            batch = client.batch()
            for tid, tp in positions.items():
                ref = client.collection(COLLECTION_POSITIONS).document(tid)
                batch.set(ref, tp.to_firestore(), merge=True)
            batch.commit()
            firestore_ok = True
            firestore_error = ""
        except Exception as exc:
            firestore_error = f"{type(exc).__name__}:{exc}"

    return persist_result(local_ok=True, firestore_ok=firestore_ok, firestore_error=firestore_error)


def save_team_positions(team_positions: TeamPositions) -> dict[str, Any]:
    all_pos = load_all_positions()
    team_positions.updated_at = now_kst_iso()
    all_pos[team_positions.team_id] = team_positions
    return save_all_positions(all_pos)


def create_empty_positions(team_id: str) -> TeamPositions:
    return TeamPositions(team_id=team_id)  # type: ignore[arg-type]


def positions_initialized() -> bool:
    all_pos = load_all_positions()
    return all(tid in all_pos for tid in TEAM_IDS)
