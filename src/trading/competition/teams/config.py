"""Role-based model configuration (env-driven, no hardcoded model IDs)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Provider = Literal["gemini", "deepseek", "mock"]


@dataclass(frozen=True)
class ModelRoleConfig:
    provider: Provider
    model_env_key: str
    default_model: str = "placeholder"


# Spec §5 role routing — actual IDs from env when available
ROLE_CONFIG: dict[str, ModelRoleConfig] = {
    "A_MAIN": ModelRoleConfig("deepseek", "COMPETITION_A_MAIN_MODEL", "deepseek-chat"),
    "A_PARTNER": ModelRoleConfig("gemini", "COMPETITION_A_PARTNER_MODEL", "gemini-flash-placeholder"),
    "B_MAIN": ModelRoleConfig("gemini", "COMPETITION_B_MAIN_MODEL", "gemini-flash-placeholder"),
    "B_PARTNER": ModelRoleConfig("deepseek", "COMPETITION_B_PARTNER_MODEL", "deepseek-chat"),
    "C_MAIN": ModelRoleConfig("deepseek", "COMPETITION_C_MAIN_MODEL", "deepseek-chat"),
    "C_VALIDATOR": ModelRoleConfig("gemini", "COMPETITION_C_VALIDATOR_MODEL", "gemini-flash-placeholder"),
    "D_MAIN": ModelRoleConfig("gemini", "COMPETITION_D_MAIN_MODEL", "gemini-flash-placeholder"),
    "D_VALIDATOR": ModelRoleConfig("deepseek", "COMPETITION_D_VALIDATOR_MODEL", "deepseek-reasoner-placeholder"),
    "EVENT_ANALYZER": ModelRoleConfig("gemini", "GEMINI_EVENT_ANALYZER_MODEL", "gemini-flash-placeholder"),
}


def resolve_model(role: str, *, force_mock: bool = False) -> tuple[Provider, str]:
    cfg = ROLE_CONFIG[role]
    if force_mock or os.getenv("COMPETITION_USE_MOCK_LLM", "").lower() in ("1", "true", "yes"):
        return "mock", "mock"
    model = os.getenv(cfg.model_env_key) or cfg.default_model
    if model.endswith("-placeholder"):
        return "mock", model
    return cfg.provider, model


def provider_available(provider: Provider) -> bool:
    if provider == "mock":
        return True
    if provider == "gemini":
        try:
            import config as app_config

            return bool(getattr(app_config, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY"))
        except Exception:
            return bool(os.getenv("GEMINI_API_KEY"))
    if provider == "deepseek":
        return bool(os.getenv("DEEPSEEK_API_KEY"))
    return False
