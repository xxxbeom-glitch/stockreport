"""watchlist 제안서 → kr_watchlist.json 반영 (SAFE_MODE 게이트)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from data.kr_watchlist import save_kr_watchlist_raw

logger = logging.getLogger("weekly_watchlist.watchlist_apply")


def apply_watchlist_from_proposal(
    proposal_path: str | Path,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """
    제안 JSON을 kr_watchlist.json에 반영.
    apply=False 또는 SAFE_MODE 시 파일 미수정.
    """
    from utils.safe_mode import can_apply_watchlist

    path = Path(proposal_path)
    if not path.is_file():
        return {"ok": False, "error": f"proposal not found: {path}"}

    if not apply:
        return {
            "ok": True,
            "applied": False,
            "reason": "apply=False (proposal only)",
        }

    if not can_apply_watchlist(explicit_cli=True):
        logger.warning("watchlist apply blocked by SAFE_MODE")
        return {
            "ok": True,
            "applied": False,
            "reason": "SAFE_MODE: use WATCHLIST_AUTO_APPLY=true with --apply-watchlist",
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}

    new_data = payload.get("watchlist") or payload.get("sectors")
    if not isinstance(new_data, dict):
        return {
            "ok": False,
            "error": "proposal has no watchlist/sectors payload to apply",
        }

    if "sectors" in new_data:
        watchlist_body = {"version": payload.get("version", 2), "sectors": new_data}
    else:
        watchlist_body = new_data

    saved = save_kr_watchlist_raw(watchlist_body, explicit_apply=True)
    return {
        "ok": saved,
        "applied": saved,
        "path": str(path),
    }


def apply_candidates_to_watchlist(
    _candidate_payload: dict[str, Any] | list[dict[str, Any]],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """신규 후보 → watchlist 자동 교체 (기본 금지, JSON 제안만)."""
    from utils.safe_mode import can_replace_candidates

    if not apply:
        return {"ok": True, "applied": False, "reason": "proposal only"}
    if not can_replace_candidates(explicit_cli=True):
        return {
            "ok": True,
            "applied": False,
            "reason": "SAFE_MODE: CANDIDATE_AUTO_REPLACE=false",
        }
    return {
        "ok": False,
        "applied": False,
        "reason": "candidate watchlist replace not implemented",
    }
