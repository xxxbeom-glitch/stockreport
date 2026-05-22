"""📈 오늘 매수 후보 Slack."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from agents.kr_intraday_slack.constants import SCAN_SLOTS, SLOT_PHASE_LABEL
from agents.kr_intraday_slack.message_tone import sanitize_slack_mrkdwn, slack_display_label
from agents.market_metrics.ohlcv_ratios import (
    trading_value_ratio_label,
    volume_ratio_label,
)


def _kst_now_str() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")


def _slot_header(slot: str) -> str:
    clock, _ = SCAN_SLOTS.get(slot, ("10:25", ""))
    phase = SLOT_PHASE_LABEL.get(slot, "장전")
    return f"[{phase} {clock}]"


def build_morning_buy_empty_slack(*, slot: str, scanned: int) -> str:
    title = f"📈 {_slot_header(slot)} 오늘 매수 후보"
    return sanitize_slack_mrkdwn(
        f"{title}\n\n"
        f"분석 기준: {_slot_header(slot)}\n"
        f"발송 시각: {_kst_now_str()}\n"
        f"확인 종목: {scanned}개 (관심종목 + 임시 관찰)\n\n"
        "오늘은 현재 기준으로 진입을 검토할 만한 종목이 없습니다.\n"
        "무리한 진입 없이 다음 기회를 기다립니다."
    )


def _format_stock(row: dict[str, Any]) -> str:
    name = row.get("name", "")
    price = row.get("current_price_fmt") or ""
    decision = slack_display_label(str(row.get("ai_decision") or row.get("status") or ""))
    if decision in ("추격매수 위험",):
        decision = "추격 금지"
    lines = [
        f"• *{name}*",
        f"현재가: {price}",
        f"판단: {decision}",
    ]
    er = str(row.get("entry_range") or "").strip()
    if er:
        lines.append(f"진입 검토 가격대: {er}")
    lines.append(volume_ratio_label(row.get("volume_ratio_20d"), intraday=True))
    lines.append(trading_value_ratio_label(row.get("trading_value_ratio_20d"), intraday=True))
    lines.append(
        f"수급: 외국인 {row.get('foreign_net_eok', 0)}억 / 기관 {row.get('inst_net_eok', 0)}억"
    )
    if row.get("ai_reason"):
        lines.append(f"이유: {row['ai_reason']}")
    if row.get("ai_cancel_condition"):
        lines.append(f"취소/위험: {row['ai_cancel_condition']}")
    if row.get("grok_note") or row.get("mention_summary"):
        lines.append(f"최신 이슈: {row.get('grok_note') or row.get('mention_summary')}")
    return "\n".join(lines)


def build_morning_buy_slack(
    *,
    slot: str,
    send_rows: list[dict[str, Any]],
    scanned: int,
) -> str:
    title = f"📈 {_slot_header(slot)} 오늘 매수 후보"
    header = [
        title,
        "",
        f"분석 기준: {_slot_header(slot)}",
        f"발송 시각: {_kst_now_str()}",
        f"확인 종목: {scanned}개 / 후보 {len(send_rows)}개",
        "",
    ]
    if not send_rows:
        return build_morning_buy_empty_slack(slot=slot, scanned=scanned)
    blocks = [_format_stock(r) for r in send_rows]
    return sanitize_slack_mrkdwn("\n".join(header) + "\n\n".join(blocks))
