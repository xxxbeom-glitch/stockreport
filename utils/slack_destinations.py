"""실사용 Slack 목적별 채널·웹훅 (매수 후보 vs 관심종목 새벽 리포트)."""

from __future__ import annotations

import os

import config

PURPOSE_BUY_CANDIDATE = "buy_candidate"
PURPOSE_WATCHLIST_REPORT = "watchlist_report"


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def is_incoming_webhook(destination: str) -> bool:
    text = (destination or "").strip().lower()
    return text.startswith("https://hooks.slack.com/") or text.startswith("http://") and "hooks.slack.com" in text


def resolve_buy_candidate_destination() -> str:
    """오늘 매수 후보 알림 (장전·장후 후보 스캔 포함)."""
    return _first_env(
        "SLACK_BUY_CANDIDATE_WEBHOOK",
        "SLACK_BUY_CANDIDATE_CHANNEL",
        "SLACK_CHANNEL_KR",
    ) or (config.SLACK_CHANNEL_KR or "").strip()


def resolve_watchlist_report_destination() -> str:
    """관심종목 새벽 리포트."""
    return _first_env(
        "SLACK_WATCHLIST_REPORT_WEBHOOK",
        "SLACK_WATCHLIST_REPORT_CHANNEL",
    )
