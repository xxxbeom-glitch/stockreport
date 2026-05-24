"""Team account storage — Firestore + local JSON mirror."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.trading.competition.constants import (
    ACCOUNT_STATUS_ACTIVE,
    COLLECTION_ACCOUNTS,
    INITIAL_CASH_KRW,
    TEAM_IDS,
)
from src.trading.competition.models import TeamAccount, now_kst_iso
from src.trading.competition.storage.base import (
    ensure_local_dir,
    firestore_client,
    load_json_file,
    persist_result,
    save_json_file,
)

ACCOUNTS_PATH = ensure_local_dir() / "accounts.json"


def _default_accounts_doc() -> dict[str, Any]:
    return {"teams": {}, "updated_at": ""}


def load_all_accounts() -> dict[str, TeamAccount]:
    raw = load_json_file(ACCOUNTS_PATH, _default_accounts_doc())
    teams = raw.get("teams") or {}
    return {tid: TeamAccount.from_dict(data) for tid, data in teams.items()}


def load_account(team_id: str) -> TeamAccount | None:
    return load_all_accounts().get(team_id)


def save_accounts(accounts: dict[str, TeamAccount]) -> dict[str, Any]:
    payload = {
        "teams": {tid: acc.to_firestore() for tid, acc in accounts.items()},
        "updated_at": now_kst_iso(),
    }
    save_json_file(ACCOUNTS_PATH, payload)

    client, status = firestore_client()
    firestore_ok = False
    firestore_error = status.get("error", "")
    if client:
        try:
            batch = client.batch()
            for tid, acc in accounts.items():
                ref = client.collection(COLLECTION_ACCOUNTS).document(tid)
                batch.set(ref, acc.to_firestore(), merge=True)
            batch.commit()
            firestore_ok = True
            firestore_error = ""
        except Exception as exc:
            firestore_error = f"{type(exc).__name__}:{exc}"

    return persist_result(local_ok=True, firestore_ok=firestore_ok, firestore_error=firestore_error)


def save_account(account: TeamAccount) -> dict[str, Any]:
    accounts = load_all_accounts()
    accounts[account.team_id] = account
    return save_accounts(accounts)


def accounts_exist() -> bool:
    accounts = load_all_accounts()
    return all(tid in accounts for tid in TEAM_IDS)


def create_initial_account(team_id: str) -> TeamAccount:
    ts = now_kst_iso()
    return TeamAccount(
        team_id=team_id,  # type: ignore[arg-type]
        cash_krw=INITIAL_CASH_KRW,
        total_assets_krw=INITIAL_CASH_KRW,
        status=ACCOUNT_STATUS_ACTIVE,
        initial_cash_krw=INITIAL_CASH_KRW,
        started_at=ts,
        updated_at=ts,
    )
