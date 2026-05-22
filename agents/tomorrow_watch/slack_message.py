"""🌙 내일 볼 종목 Slack."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from agents.market_metrics.ohlcv_ratios import (
    trading_value_ratio_label,
    volume_ratio_label,
)
from agents.kr_intraday_slack.message_tone import sanitize_slack_mrkdwn


def _kst_now_str() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")


def build_tomorrow_watch_slack(
    *,
    analysis_clock: str,
    picks: list[dict[str, Any]],
    scanned: int,
    quant_passed: int,
) -> str:
    sent_at = _kst_now_str()
    title = "🌙 내일 볼 종목"
    header = [
        title,
        "",
        f"분석 기준: {analysis_clock}",
        f"발송 시각: {sent_at}",
        f"스캔: {scanned}종목 / 정량 통과: {quant_passed}종목",
        "",
    ]
    if not picks:
        body = (
            "오늘 새롭게 추가할 관찰 후보는 없습니다.\n"
            "거래·수급 조건을 충족한 신규 종목이 확인되지 않았습니다."
        )
        return sanitize_slack_mrkdwn("\n".join(header) + body)

    blocks: list[str] = []
    for row in picks:
        name = row.get("name", "")
        price = row.get("current_price_fmt") or row.get("current_price", "")
        lines = [
            f"• *{name}*",
            f"현재가: {price}",
            f"최종: {row.get('final_status', '관찰 후보 등록')}",
            f"투표: {row.get('vote_summary', {})} / trend: {row.get('trend_score', '-')}",
            f"이유: {row.get('deepseek_final_reason', row.get('selection_reason', ''))}",
            volume_ratio_label(row.get("volume_ratio_20d")),
            trading_value_ratio_label(row.get("trading_value_ratio_20d")),
            f"수급: 외국인 {row.get('foreign_net_eok', 0)}억 / 기관 {row.get('inst_net_eok', 0)}억",
        ]
        if row.get("dart_disclosure_summary"):
            lines.append(f"새 공시: {row['dart_disclosure_summary']}")
        if row.get("grok_issue_summary"):
            lines.append(f"이슈: {row['grok_issue_summary']}")
        if row.get("risk_notes"):
            lines.append(f"주의: {row['risk_notes']}")
        ap = row.get("aftermarket_priority")
        lines.append(
            "애프터마켓 우선 확인: 예"
            if ap
            else "애프터마켓 우선 확인: 보통"
        )
        if row.get("next_day_check"):
            lines.append(f"내일 확인: {row['next_day_check']}")
        blocks.append("\n".join(lines))

    return sanitize_slack_mrkdwn("\n".join(header) + "\n".join(blocks))


def build_tomorrow_watch_empty_slack(*, analysis_clock: str, scanned: int) -> str:
    return build_tomorrow_watch_slack(
        analysis_clock=analysis_clock,
        picks=[],
        scanned=scanned,
        quant_passed=0,
    )
