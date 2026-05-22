"""운영 플래그 — 매일 투자 후보(DAILY_PICK) vs 관심종목 재판단(WATCHLIST_REVIEW) 분리."""

from __future__ import annotations

import os
from typing import Callable

# ── 매일 투자 후보 (장중 Slack) ──
DAILY_PICK_AUTO_SEND_DEFAULT = True

# ── 관심종목 재판단/재구성 (주간) ──
WATCHLIST_REVIEW_AUTO_SEND_DEFAULT = False
WATCHLIST_AUTO_APPLY_DEFAULT = False
CANDIDATE_AUTO_REPLACE_DEFAULT = False

# 하위 호환 (주간 재판단용 — 신규 코드는 WATCHLIST_REVIEW_AUTO_SEND 사용)
SLACK_AUTO_SEND_DEFAULT = WATCHLIST_REVIEW_AUTO_SEND_DEFAULT
SAFE_MODE_ENV = "SAFE_MODE"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def is_safe_mode() -> bool:
    """
    레거시: 관심종목 재판단 자동화만 제한할 때 true.
    DAILY_PICK 발송에는 사용하지 않음.
    """
    raw = os.getenv(SAFE_MODE_ENV)
    if raw is None or raw.strip() == "":
        return False
    return raw.strip().lower() in ("1", "true", "yes", "on")


def daily_pick_auto_send_enabled() -> bool:
    """장중·일일 '오늘 볼 만한 종목' Slack 스케줄 발송."""
    return _env_bool("DAILY_PICK_AUTO_SEND", DAILY_PICK_AUTO_SEND_DEFAULT)


def watchlist_review_auto_send_enabled() -> bool:
    """주간 관심종목 재평가 Slack 자동 발송."""
    return _env_bool("WATCHLIST_REVIEW_AUTO_SEND", WATCHLIST_REVIEW_AUTO_SEND_DEFAULT)


def watchlist_auto_apply_enabled() -> bool:
    return _env_bool("WATCHLIST_AUTO_APPLY", WATCHLIST_AUTO_APPLY_DEFAULT)


def candidate_auto_replace_enabled() -> bool:
    return _env_bool("CANDIDATE_AUTO_REPLACE", CANDIDATE_AUTO_REPLACE_DEFAULT)


def slack_auto_send_enabled() -> bool:
    """레거시 alias → WATCHLIST_REVIEW_AUTO_SEND."""
    return watchlist_review_auto_send_enabled()


def can_send_daily_pick_slack(
    *,
    explicit_cli: bool = False,
    scheduled: bool = False,
) -> bool:
    """
    매일 투자 후보 메시지 Slack 발송.
    스케줄·--send 모두 DAILY_PICK_AUTO_SEND 로만 제어 (SAFE_MODE 무관).
    """
    if not (explicit_cli or scheduled):
        return False
    return daily_pick_auto_send_enabled()


def can_send_watchlist_review_slack(
    *,
    explicit_cli: bool = False,
    scheduled: bool = False,
) -> bool:
    """관심종목 새벽 리포트 Slack — 스케줄 또는 --send-slack + WATCHLIST_REVIEW_AUTO_SEND."""
    if not (explicit_cli or scheduled):
        return False
    return watchlist_review_auto_send_enabled()


def can_send_slack(*, explicit_cli: bool = False) -> bool:
    """레거시: 주간 재판단 Slack 게이트."""
    return can_send_watchlist_review_slack(explicit_cli=explicit_cli)


def can_apply_watchlist(*, explicit_cli: bool = False) -> bool:
    """--apply-watchlist + WATCHLIST_AUTO_APPLY=true 일 때만 kr_watchlist.json 반영."""
    if not explicit_cli:
        return False
    return watchlist_auto_apply_enabled()


def can_replace_candidates(*, explicit_cli: bool = False) -> bool:
    if not explicit_cli:
        return False
    return candidate_auto_replace_enabled()


def can_send_candidate_slack(*, explicit_cli: bool = False) -> bool:
    """신규 후보 스캔 테스트 — 수동 --send-slack 시에만 (자동 스케줄·env 게이트 없음)."""
    return explicit_cli


def print_daily_pick_status(emit: Callable[[str], None] | None = None) -> None:
    out = emit or print
    if daily_pick_auto_send_enabled():
        out("[DAILY_PICK] Slack 발송 가능")
    else:
        out("[DAILY_PICK] Slack 발송 비활성 (DAILY_PICK_AUTO_SEND=false)")


def print_watchlist_review_status(emit: Callable[[str], None] | None = None) -> None:
    out = emit or print
    if watchlist_review_auto_send_enabled():
        out("[WATCHLIST_REVIEW] 자동 발송 허용 (WATCHLIST_REVIEW_AUTO_SEND=true)")
    else:
        out("[WATCHLIST_REVIEW] 자동 발송 중지")
    if watchlist_auto_apply_enabled():
        out("[WATCHLIST_REVIEW] 자동 수정 허용 (WATCHLIST_AUTO_APPLY=true)")
    else:
        out("[WATCHLIST_REVIEW] 자동 수정 중지")
    if candidate_auto_replace_enabled():
        out("[CANDIDATES] 자동 교체 허용 (CANDIDATE_AUTO_REPLACE=true)")
    elif not candidate_auto_replace_enabled():
        out("[CANDIDATES] 자동 교체 중지 — 제안만 생성")


def print_candidate_scan_status(emit: Callable[[str], None] | None = None) -> None:
    out = emit or print
    out("[CANDIDATES] 제안만 생성 (watchlist·kr_watchlist.json 미수정)")
    if not candidate_auto_replace_enabled():
        out("[CANDIDATES] 자동 교체 중지")


def print_safe_mode_banner(emit: Callable[[str], None] | None = None) -> None:
    """레거시 — 주간 재판단 상태만 (장중은 print_daily_pick_status 사용)."""
    print_watchlist_review_status(emit=emit)
