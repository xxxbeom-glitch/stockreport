"""📈 오늘 매수 후보 Slack — 요약 1건 + 종목별 상세 각 1건."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.kr_intraday_slack.constants import SCAN_SLOTS, SLOT_PHASE_LABEL
from agents.kr_intraday_slack.entry_price import has_valid_entry_range
from agents.kr_intraday_slack.message_tone import (
    _format_price_line,
    _format_watch_zone,
    sanitize_slack_mrkdwn,
    scrub_easy_language,
)

def _kst_now_str() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")


def _slot_header(slot: str) -> str:
    clock, _ = SCAN_SLOTS.get(slot, ("10:25", ""))
    phase = SLOT_PHASE_LABEL.get(slot, "장전")
    return f"[{phase} {clock}]"


def _pct_vs_avg(ratio: float | None) -> int | None:
    if ratio is None:
        return None
    try:
        return int(round((float(ratio) - 1.0) * 100))
    except (TypeError, ValueError):
        return None


def _volume_interest_summary(ratio: float | None) -> str:
    if ratio is None:
        return "거래량 비교가 어려워 추가 확인이 필요함"
    if ratio < 0.9:
        return "관심이 아직 부족함"
    if ratio <= 1.15:
        return "보통보다 조금 관심이 많음"
    return "평소보다 돈이 강하게 들어오는 중"


def _trading_value_interest_summary(ratio: float | None) -> str:
    if ratio is None:
        return "거래대금 비교가 어려움"
    if ratio < 0.9:
        return "돈 유입이 아직 약함"
    if ratio <= 1.15:
        return "평소보다 조금 돈이 들어오는 중"
    return "평소보다 돈이 강하게 들어오는 중"


def _supply_line(label: str, net_eok: Any) -> str:
    try:
        v = float(net_eok or 0)
    except (TypeError, ValueError):
        v = 0.0
    abs_v = abs(v)
    if abs_v < 0.5:
        return f"{label}은 큰 움직임 없음"
    action = "사고 있음" if v > 0 else "팔고 있음"
    return f"{label}은 {abs_v:.0f}억 원어치 {action}"


def _parse_entry_low(row: dict[str, Any]) -> int:
    try:
        lo = int(row.get("entry_low") or 0)
    except (TypeError, ValueError):
        lo = 0
    if lo > 0:
        return lo
    er = str(row.get("entry_range") or "")
    m = re.search(r"([\d,]+)원\s*~", er)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


def easy_conclusion(row: dict[str, Any]) -> str:
    decision = str(row.get("ai_decision") or row.get("status") or "").strip()
    if row.get("is_chasing") or decision in ("추격 금지", "추격매수 위험"):
        return "지금 가격은 많이 올라 있어서, 무리해서 따라 사지 말 것"
    if decision in ("진입 검토", "예약가 후보"):
        zone = _format_watch_zone(row)
        if zone:
            return "바로 사지 말고, 제시 가격까지 내려오면 매수 검토"
        return "바로 사지 말고, 가격과 거래 흐름을 다시 확인한 뒤 검토"
    if decision in ("조금 더 관찰", "관찰 강화", "눌림 확인"):
        return "아직 확신이 부족해서, 조금 더 지켜본 뒤 판단"
    if decision == "오늘은 패스":
        return "오늘은 무리해서 들어가지 않는 편이 낫음"
    return "급하게 따라 사지 말고, 아래 가격·주의 조건을 먼저 확인"


def _stop_lines(row: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    entry_low = _parse_entry_low(row)
    if entry_low > 0:
        stop_price = max(int(entry_low * 0.97), entry_low - 500)
        lines.append(f"{stop_price:,}원 아래로 내려가면 더 보지 말고 중단")

    cancel = scrub_easy_language(str(row.get("ai_cancel_condition") or "")).strip()
    rule_warn = scrub_easy_language(
        str(row.get("rule_warning_condition") or "")
    ).strip()

    if "거래" in cancel or "급감" in cancel or "거래" in rule_warn or "급감" in rule_warn:
        lines.append("사기 전에 거래가 갑자기 줄어들면 매수 취소")
    elif cancel and len(cancel) >= 12:
        if cancel not in lines:
            lines.append(cancel)
    elif rule_warn and len(rule_warn) >= 12:
        if "이탈" in rule_warn:
            lines.append(rule_warn.replace("이탈 또는", "아래로 내려가면 중단, 또는"))
        else:
            lines.append(rule_warn)

    if not lines:
        lines.append("가격이 크게 깨지거나 거래가 갑자기 줄면 오늘은 넘기기")
    return lines[:3]


def _why_candidate_text(row: dict[str, Any]) -> str:
    reason = scrub_easy_language(str(row.get("ai_reason") or "")).strip()
    caution_parts: list[str] = []
    try:
        foreign = float(row.get("foreign_net_eok") or 0)
    except (TypeError, ValueError):
        foreign = 0.0
    if foreign < -5 and "외국인" not in reason:
        caution_parts.append("외국인이 팔고 있으므로 급하게 따라 사지는 말 것")

    if reason and caution_parts:
        caution = " ".join(caution_parts[:2])
        return f"{reason.rstrip('.')}. 다만 {caution}."
    if reason:
        return reason if reason.endswith((".", "!", "?")) else f"{reason}."
    if caution_parts:
        return caution_parts[0]
    return "오늘 거래 흐름을 다시 확인할 만한 후보이지만, 무리한 추격은 피하는 편이 좋음."


def build_morning_buy_stock_detail(row: dict[str, Any]) -> str:
    """종목 상세 1건."""
    name = str(row.get("name", "")).strip()
    lines: list[str] = [f"● *{name}*"]

    price = _format_price_line(row)
    if price:
        lines.append(f"현재가: {price}")

    lines.append("")
    lines.append(f"결론: {easy_conclusion(row)}")
    lines.append("")

    zone = _format_watch_zone(row)
    if zone and has_valid_entry_range(
        str(row.get("entry_range") or ""),
        entry_low=row.get("entry_low"),
        entry_high=row.get("entry_high"),
    ):
        lines.append("✅ 이 가격이면 사도 됨")
        lines.append(zone)
        lines.append("")

    lines.append("🚫 이러면 사지 말거나 팔기")
    lines.extend(_stop_lines(row))
    lines.append("")

    vol_ratio = row.get("volume_ratio_20d")
    tv_ratio = row.get("trading_value_ratio_20d")
    lines.append("🔥 오늘 관심도")
    lines.append(_volume_interest_summary(vol_ratio))
    vol_pct = _pct_vs_avg(vol_ratio)
    if vol_pct is not None:
        sign = "많음" if vol_pct >= 0 else "적음"
        lines.append(f"- 거래량: 최근 평균보다 {abs(vol_pct)}% {sign}")
    tv_pct = _pct_vs_avg(tv_ratio)
    if tv_pct is not None:
        sign = "많음" if tv_pct >= 0 else "적음"
        lines.append(f"- 거래대금: 최근 평균보다 {abs(tv_pct)}% {sign}")
    lines.append("")

    lines.append("💰 큰손 흐름")
    lines.append(f"- {_supply_line('외국인', row.get('foreign_net_eok'))}")
    lines.append(f"- {_supply_line('기관', row.get('inst_net_eok'))}")
    lines.append("")

    lines.append("왜 후보인가?")
    lines.append(_why_candidate_text(row))

    return sanitize_slack_mrkdwn("\n".join(lines))


def build_morning_buy_summary(
    *,
    slot: str,
    send_rows: list[dict[str, Any]],
    scanned: int,
) -> str:
    """전체 요약 1건."""
    n = len(send_rows)
    header = _slot_header(slot)
    lines = [
        f"📈 {header} 오늘 매수 후보",
        "",
        f"분석 기준: {header}",
        f"발송 시각: {_kst_now_str()}",
        f"확인 종목: {scanned}개 / 후보 {n}개",
        "",
    ]
    if n == 0:
        lines.append("오늘은 현재 기준으로 진입을 검토할 만한 종목이 없습니다.")
        lines.append("무리한 진입 없이 다음 기회를 기다립니다.")
    elif n == 1:
        lines.append("오늘 확인할 후보 1개입니다.")
        lines.append("이어서 살 만한 가격과 주의할 조건을 보냅니다.")
    else:
        lines.append(f"오늘 확인할 후보 {n}개입니다.")
        lines.append("종목별로 살 만한 가격과 주의할 조건을 이어서 보냅니다.")
    return sanitize_slack_mrkdwn("\n".join(lines))


def build_morning_buy_empty_slack(*, slot: str, scanned: int) -> str:
    return build_morning_buy_summary(slot=slot, send_rows=[], scanned=scanned)


def build_morning_buy_slack_bundle(
    *,
    slot: str,
    send_rows: list[dict[str, Any]],
    scanned: int,
) -> dict[str, Any]:
    """
    summary 1건 + 종목별 detail N건.
    messages = [summary, *details] 순서.
    """
    summary = build_morning_buy_summary(slot=slot, send_rows=send_rows, scanned=scanned)
    details = [build_morning_buy_stock_detail(r) for r in send_rows]
    return {
        "summary": summary,
        "detail_messages": details,
        "messages": [summary, *details],
    }


def build_morning_buy_slack(
    *,
    slot: str,
    send_rows: list[dict[str, Any]],
    scanned: int,
) -> str:
    """하위 호환 — 요약만 (전체 본문 합치지 않음)."""
    return build_morning_buy_summary(slot=slot, send_rows=send_rows, scanned=scanned)
