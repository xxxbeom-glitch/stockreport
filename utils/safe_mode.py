"""운영 안전 모드 — watchlist·Slack·후보 자동 반영 일시 중지 (플래그로 재활성화)."""

from __future__ import annotations

import os
from typing import Callable

# 기본값: 전부 비활성 (환경변수 true/1/yes 로만 켬)
WATCHLIST_AUTO_APPLY_DEFAULT = False
SLACK_AUTO_SEND_DEFAULT = False
CANDIDATE_AUTO_REPLACE_DEFAULT = False

# SAFE_MODE=true 이면 위 세 플래그도 강제 OFF
SAFE_MODE_ENV = "SAFE_MODE"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def is_safe_mode() -> bool:
    """전역 안전 모드(기본 on) — true면 자동 apply/send/replace 차단."""
    raw = os.getenv(SAFE_MODE_ENV)
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def watchlist_auto_apply_enabled() -> bool:
    return _env_bool("WATCHLIST_AUTO_APPLY", WATCHLIST_AUTO_APPLY_DEFAULT)


def slack_auto_send_enabled() -> bool:
    return _env_bool("SLACK_AUTO_SEND", SLACK_AUTO_SEND_DEFAULT)


def candidate_auto_replace_enabled() -> bool:
    return _env_bool("CANDIDATE_AUTO_REPLACE", CANDIDATE_AUTO_REPLACE_DEFAULT)


def can_apply_watchlist(*, explicit_cli: bool = False) -> bool:
    """
    기본 False. --apply-watchlist 시에만 반영 시도.
    SAFE_MODE(기본 on)에서는 WATCHLIST_AUTO_APPLY=true 일 때만 허용.
    """
    if not explicit_cli:
        return False
    if is_safe_mode():
        return watchlist_auto_apply_enabled()
    return True


def can_send_slack(*, explicit_cli: bool = False) -> bool:
    """
    기본 False. --send-slack / --send 명시 시에만 발송.
    SAFE_MODE에서는 SLACK_AUTO_SEND=true 일 때만 허용.
    """
    if not explicit_cli:
        return False
    if is_safe_mode():
        return slack_auto_send_enabled()
    return True


def can_replace_candidates(*, explicit_cli: bool = False) -> bool:
    """신규 후보 → watchlist 자동 교체 (기본 금지)."""
    if not explicit_cli:
        return False
    if is_safe_mode():
        return candidate_auto_replace_enabled()
    return True


def print_safe_mode_banner(
    emit: Callable[[str], None] | None = None,
) -> None:
    """실행 시작 시 안전 모드 상태 로그."""
    out = emit or print
    if is_safe_mode():
        out("[SAFE_MODE] SAFE_MODE=true — 자동 apply/send/replace 차단")
    if not watchlist_auto_apply_enabled():
        out("[SAFE_MODE] watchlist auto apply disabled")
    if not slack_auto_send_enabled():
        out("[SAFE_MODE] slack auto send disabled")
    if not candidate_auto_replace_enabled():
        out("[SAFE_MODE] candidate auto replace disabled")
