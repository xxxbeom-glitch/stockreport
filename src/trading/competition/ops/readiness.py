"""Live operations readiness checks."""

from __future__ import annotations

import os
from typing import Any

from src.trading.competition.teams.config import ROLE_CONFIG, provider_available, resolve_model

# Token-saving model recommendations (live ops)
RECOMMENDED_MODELS: dict[str, str] = {
    "COMPETITION_A_MAIN_MODEL": "deepseek-v4-flash",
    "COMPETITION_A_PARTNER_MODEL": "gemini-2.5-flash-lite",
    "COMPETITION_B_MAIN_MODEL": "gemini-2.5-flash-lite",
    "COMPETITION_B_PARTNER_MODEL": "deepseek-v4-flash",
    "COMPETITION_C_MAIN_MODEL": "deepseek-v4-flash",
    "COMPETITION_C_VALIDATOR_MODEL": "gemini-2.5-flash-lite",
    "COMPETITION_D_MAIN_MODEL": "gemini-2.5-flash-lite",
    "COMPETITION_D_VALIDATOR_MODEL": "deepseek-v4-pro",
    "GEMINI_EVENT_ANALYZER_MODEL": "gemini-2.5-flash-lite",
}


def _allow_local_mirror_only() -> bool:
    """local_mirror 단독 허용 — 로컬 dry-run/test 전용 (GitHub Actions live 운용 금지)."""
    return os.getenv("COMPETITION_ALLOW_LOCAL_MIRROR", "").lower() in ("1", "true", "yes")


def check_live_readiness(*, allow_local_mirror: bool | None = None) -> dict[str, Any]:
    """
    Returns readiness report. Live ops MUST NOT start when ready=False.
    Never includes secret values.

    allow_local_mirror: True면 Firebase 미연결을 blocker에서 제외 (로컬 dry-run/test).
        None이면 COMPETITION_ALLOW_LOCAL_MIRROR env를 따름.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    local_mirror_ok = allow_local_mirror if allow_local_mirror is not None else _allow_local_mirror_only()

    mock_forced = os.getenv("COMPETITION_USE_MOCK_LLM", "").lower() in ("1", "true", "yes")
    if mock_forced:
        blockers.append("COMPETITION_USE_MOCK_LLM is enabled")

    roles_status: dict[str, Any] = {}
    for role, cfg in ROLE_CONFIG.items():
        provider, model = resolve_model(role, force_mock=False)
        avail = provider_available(provider) and not model.endswith("-placeholder")
        roles_status[role] = {
            "provider": cfg.provider,
            "env_key": cfg.model_env_key,
            "resolved_provider": provider,
            "model_configured": avail,
        }
        if not avail and role != "EVENT_ANALYZER":
            blockers.append(f"{role}: set {cfg.model_env_key} and API key for {cfg.provider}")

    if not provider_available("gemini"):
        blockers.append("GEMINI_API_KEY (or config.GEMINI_API_KEY) required for Gemini roles")
    if not provider_available("deepseek"):
        blockers.append("DEEPSEEK_API_KEY required for DeepSeek roles")

    firebase_ok = False
    firebase_error = ""
    try:
        from src.trading.competition.storage.base import firestore_client

        client, status = firestore_client()
        firebase_ok = client is not None
        firebase_error = status.get("error", "")
    except Exception as exc:
        firebase_error = type(exc).__name__

    if not firebase_ok:
        msg = (
            f"Firebase required for live ops (not local_mirror only)"
            f"{': ' + firebase_error if firebase_error else ''}"
        )
        if local_mirror_ok:
            warnings.append(f"{msg} — allowed for local dry-run/test only")
        else:
            blockers.append(msg)

    slack_webhook = bool(os.getenv("COMPETITION_SLACK_WEBHOOK") or os.getenv("SLACK_WEBHOOK_URL"))
    if not slack_webhook:
        warnings.append("Slack webhook not set — notifications dry-run only")

    ready = len(blockers) == 0
    return {
        "ready_for_live_ops": ready,
        "blockers": blockers,
        "warnings": warnings,
        "roles": roles_status,
        "firebase": {
            "configured": firebase_ok,
            "required_for_live_ops": True,
            "local_mirror_only_allowed": local_mirror_ok,
        },
        "slack": {"webhook_configured": slack_webhook},
        "recommended_models": dict(RECOMMENDED_MODELS),
        "required_env": {
            "llm": ["COMPETITION_USE_MOCK_LLM=0", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"]
            + [f"{k}={v}" for k, v in RECOMMENDED_MODELS.items()],
            "firebase": [
                "FIREBASE_STORAGE_BUCKET",
                "GOOGLE_APPLICATION_CREDENTIALS or ADC",
                "(live ops: COMPETITION_ALLOW_LOCAL_MIRROR must be unset)",
            ],
            "slack": ["COMPETITION_SLACK_WEBHOOK or SLACK_WEBHOOK_URL"],
            "local_test_only": ["COMPETITION_ALLOW_LOCAL_MIRROR=1"],
        },
    }
