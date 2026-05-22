"""주간 관심종목 업데이트 파이프라인."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data.kr_market import get_trading_date

from .sector_mood import judge_weekly_sector_mood
from .weekly_metrics import collect_weekly_metrics
from .weekly_report import build_slack_text, write_outputs
from .weekly_review import run_weekly_review

logger = logging.getLogger("weekly_watchlist.pipeline")


@dataclass
class WeeklyWatchlistResult:
    as_of_date: str
    metrics: list[dict[str, Any]] = field(default_factory=list)
    sector_mood: dict[str, str] = field(default_factory=dict)
    judgment: dict[str, Any] = field(default_factory=dict)
    slack_text: str = ""
    report_path: Path | None = None
    proposal_path: Path | None = None
    news_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    slack_sent: bool = False


def _resolve_as_of_date(as_of: str | None) -> str:
    if as_of:
        return as_of.replace("-", "")[:8] if len(as_of.replace("-", "")) == 8 else as_of
    raw = get_trading_date()
    if len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def run_weekly_watchlist_update(
    *,
    as_of_date: str | None = None,
    send_slack: bool = False,
    send_slack_explicit: bool = False,
    apply_watchlist: bool = False,
    use_llm: bool = True,
    slack_log_days: int = 7,
    fetch_snapshots: bool = True,
    collect_news: bool = False,
    use_existing_news: bool = False,
) -> WeeklyWatchlistResult:
    """
    load watchlist → weekly metrics → sector mood → review → MD + JSON (+ Slack)
    """
    date_iso = _resolve_as_of_date(as_of_date)
    result = WeeklyWatchlistResult(as_of_date=date_iso)

    try:
        result.metrics = collect_weekly_metrics(
            slack_log_days=slack_log_days,
            fetch_snapshots=fetch_snapshots,
        )
    except Exception as exc:
        logger.exception("메트릭 수집 실패")
        result.errors.append(f"metrics: {exc}")
        return result

    if not result.metrics:
        result.errors.append("수집된 종목 메트릭 없음")
        return result

    link_news = collect_news or use_existing_news

    if collect_news:
        try:
            from .stock_news import collect_and_save_stock_news

            result.news_path = collect_and_save_stock_news(
                date_iso,
                metrics=result.metrics,
            )
        except Exception as exc:
            logger.warning("뉴스/공시 수집 실패(리포트는 계속): %s", type(exc).__name__)
            result.errors.append(f"news: {type(exc).__name__}")

    result.sector_mood = judge_weekly_sector_mood(result.metrics)
    judgment, llm_err = run_weekly_review(
        result.metrics,
        result.sector_mood,
        as_of_date=date_iso,
        use_llm=use_llm,
    )
    if llm_err:
        result.errors.append(f"llm: {llm_err}")
    result.judgment = judgment

    if link_news:
        try:
            from .news_context import (
                attach_news_to_judgments,
                load_stock_news,
                log_news_pipeline_stats,
                run_news_llm_summaries,
            )

            news_data = load_stock_news(date_iso)
            result.judgment = attach_news_to_judgments(result.judgment, news_data)
            result.judgment = run_news_llm_summaries(
                result.judgment,
                as_of_date=date_iso,
                use_llm=use_llm,
            )
            log_news_pipeline_stats(
                news_data,
                result.judgment,
                llm_skipped=not use_llm,
            )
        except Exception as exc:
            logger.warning("뉴스 연결 실패(리포트는 계속): %s", type(exc).__name__)
            result.errors.append(f"news_link: {type(exc).__name__}")

    try:
        md_path, json_path = write_outputs(
            as_of_date=date_iso,
            metrics=result.metrics,
            sector_mood=result.sector_mood,
            judgment=judgment,
        )
        result.report_path = md_path
        result.proposal_path = json_path
    except Exception as exc:
        logger.exception("산출물 저장 실패")
        result.errors.append(f"write: {exc}")

    result.slack_text = build_slack_text(as_of_date=date_iso, judgment=judgment)

    from utils.safe_mode import can_apply_watchlist, can_send_watchlist_review_slack

    if apply_watchlist and result.proposal_path:
        from .watchlist_apply import apply_watchlist_from_proposal

        apply_result = apply_watchlist_from_proposal(
            result.proposal_path,
            apply=True,
        )
        if not apply_result.get("applied"):
            logger.info("watchlist apply skipped: %s", apply_result.get("reason"))

    may_send = send_slack and can_send_watchlist_review_slack(
        explicit_cli=send_slack_explicit
    )
    if send_slack and not may_send:
        logger.info(
            "Slack send skipped (WATCHLIST_REVIEW_AUTO_SEND=false)"
        )

    if may_send and result.slack_text:
        try:
            from slack_sender import post_watchlist_report_message

            posted = post_watchlist_report_message(result.slack_text, retries=1)
            result.slack_sent = bool(posted.get("ok"))
            if not posted.get("ok"):
                result.errors.append(f"slack: {posted.get('error', 'unknown')}")
        except Exception as exc:
            result.errors.append(f"slack: {exc}")

    return result
