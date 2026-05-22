"""알림 파이프라인 AI 모델 ID — 지정 모델만 사용, 구버전 fallback 금지."""

from __future__ import annotations

import os
from typing import Any, Callable

_POLICY_GEMINI = "gemini-3.1-pro-preview"
_POLICY_DEEPSEEK = "deepseek-v4-pro"
_POLICY_GROK = "grok-4.3"

FORBIDDEN_MODEL_IDS = frozenset(
    {
        "gemini-1.5-flash",
        "deepseek-chat",
        "grok-3",
    }
)


def _resolve_model_id(env_key: str, policy_default: str) -> str:
    raw = os.getenv(env_key, "").strip()
    if not raw or raw in FORBIDDEN_MODEL_IDS:
        return policy_default
    return raw


# 최종 지정 모델 (구버전 env 값은 무시하고 policy_default 사용)
GEMINI_MODEL_ID = _resolve_model_id("AI_SUMMARY_MODEL", _POLICY_GEMINI)
DEEPSEEK_MODEL_ID = _resolve_model_id("AI_MODEL", _POLICY_DEEPSEEK)
GROK_MODEL_ID = _resolve_model_id("AI_SOCIAL_MODEL", _POLICY_GROK)


def assert_policy_models() -> list[str]:
    """구버전 모델이 env에 있으면 경고 목록 반환."""
    warnings: list[str] = []
    for env_name, policy in (
        ("AI_SUMMARY_MODEL", _POLICY_GEMINI),
        ("AI_MODEL", _POLICY_DEEPSEEK),
        ("AI_SOCIAL_MODEL", _POLICY_GROK),
    ):
        raw = os.getenv(env_name, "").strip()
        if raw in FORBIDDEN_MODEL_IDS:
            warnings.append(
                f"{env_name}={raw} 무시됨 → policy {policy} 사용"
            )
    return warnings


def log_model_banner(emit: Callable[[str], None] | None = None) -> None:
    out = emit or print
    for w in assert_policy_models():
        out(f"[AI_POLICY] WARNING: {w}")
    out(f"Gemini model: {GEMINI_MODEL_ID}")
    out(f"DeepSeek model: {DEEPSEEK_MODEL_ID}")
    out(f"Grok model: {GROK_MODEL_ID}")


def model_status() -> dict[str, Any]:
    return {
        "gemini": GEMINI_MODEL_ID,
        "deepseek": DEEPSEEK_MODEL_ID,
        "grok": GROK_MODEL_ID,
        "forbidden_warnings": assert_policy_models(),
    }
