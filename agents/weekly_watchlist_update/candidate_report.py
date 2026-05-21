"""MVP 4 — 신규 후보 Slack·JSON 산출."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from agents.kr_intraday_slack.message_tone import (
    scrub_easy_language,
)

from .candidate_scanner import (
    CandidateScanResult,
    candidate_rows_for_slack,
    scan_summary_clock,
)

logger = logging.getLogger("weekly_watchlist.candidate_report")

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIR = ROOT / "data" / "proposals" / "candidate_scan"

_FORBIDDEN_SLACK = ("매수", "추천", "진입")


def _contains_forbidden(text: str) -> bool:
    t = scrub_easy_language(text)
    if "추천" in t or "진입" in t:
        return True
    if "매수" in t and "외국인 매수" not in t:
        return True
    return False


def _empty_slack_message(clock: str) -> str:
    return (
        "📡 오늘 새로 볼 종목\n\n"
        f"기준: {clock}\n"
        "새 후보: 0개\n"
        "_제안만 생성·watchlist 자동 수정 없음_\n\n"
        "오늘은 새로 볼 만한 종목이 뚜렷하지 않습니다.\n"
        "무리해서 찾기보다 기존 관심종목만 확인하는 편이 좋습니다."
    )


def _format_watch_zone(row: dict[str, Any]) -> str:
    er = str(row.get("entry_range") or "").strip()
    if not er:
        return ""
    return er.replace("원 ~", " ~")


def _format_stock_block(row: dict[str, Any], *, pass_today: bool) -> str:
    """종목 블록 + 체크 줄 (최대 6줄)."""
    name = str(row.get("name", "")).strip()
    if not name:
        return ""

    lines: list[str] = [f"• {name}"]
    price = str(row.get("current_price_fmt") or "").strip()
    if price:
        lines.append(f"현재가: {price}")

    zone = _format_watch_zone(row)
    if zone and not pass_today:
        lines.append(f"볼 구간: {zone}")

    reason = scrub_easy_language(str(row.get("ai_reason") or ""))
    if reason:
        lines.append(f"이유: {reason}")

    check = str(row.get("agent_check_line") or "").strip()
    if check and not pass_today:
        lines.append(check)

    caution = scrub_easy_language(str(row.get("ai_cancel_condition") or ""))
    if caution:
        lines.append(f"주의: {caution}")

    if len(lines) < 2:
        return ""
    return "\n".join(lines[:6])


def build_candidate_slack_text(scan: CandidateScanResult) -> str:
    """📡 오늘 새로 볼 종목 — Slack은 🟢/🟡 중심, 🔴 최대 1개."""
    clock = scan_summary_clock(scan.as_of_date)
    new_count = len(scan.slack_green) + len(scan.slack_yellow)

    if new_count == 0:
        return _empty_slack_message(clock)

    pass_rows = candidate_rows_for_slack(scan)[1]
    green_blocks: list[str] = []
    yellow_blocks: list[str] = []
    red_blocks: list[str] = []
    for row in scan.slack_green:
        r = {**row, "ai_decision": "진입 검토", "status": "진입 검토"}
        b = _format_stock_block(r, pass_today=False)
        if b:
            green_blocks.append(b)

    for row in scan.slack_yellow:
        r = {**row, "ai_decision": "눌림 확인", "status": "눌림 확인"}
        b = _format_stock_block(r, pass_today=False)
        if b:
            yellow_blocks.append(b)

    for row in pass_rows:
        b = _format_stock_block(row, pass_today=True)
        if b:
            red_blocks.append(b)

    lines = [
        "📡 오늘 새로 볼 종목",
        "",
        f"기준: {clock}",
        f"새 후보: {new_count}개",
        "_제안만 생성·watchlist 자동 수정 없음_",
        "",
        "🟢 지금 볼만함",
        "",
    ]
    if green_blocks:
        lines.extend(green_blocks)
        lines.append("")
    else:
        lines.append("_해당 없음_")
        lines.append("")

    lines.extend(["🟡 조금 기다림", ""])
    if yellow_blocks:
        lines.extend(yellow_blocks)
        lines.append("")
    else:
        lines.append("_해당 없음_")
        lines.append("")

    lines.extend(["🔴 오늘은 패스", ""])
    if red_blocks:
        lines.extend(red_blocks)
        lines.append("")
    else:
        lines.append("_해당 없음_")
        lines.append("")

    if scan.slack_red_overflow > 0:
        lines.append(f"_그 외 패스 {scan.slack_red_overflow}개는 JSON에 저장_")
        lines.append("")

    text = "\n".join(lines).strip()
    if _contains_forbidden(text):
        logger.warning("후보 Slack 본문에 금지어 포함 — fallback")
        text = _fallback_slack_text(scan, clock=clock, new_count=new_count)
    return text


def _fallback_slack_text(
    scan: CandidateScanResult, *, clock: str, new_count: int
) -> str:
    if new_count == 0:
        return _empty_slack_message(clock)
    lines = [
        "📡 오늘 새로 볼 종목",
        "",
        f"기준: {clock}",
        f"새 후보: {new_count}개",
        "",
    ]
    for title, rows, pass_today in (
        ("🟢 지금 볼만함", scan.slack_green, False),
        ("🟡 조금 기다림", scan.slack_yellow, False),
        ("🔴 오늘은 패스", scan.slack_red, True),
    ):
        lines.extend([title, ""])
        if rows:
            for row in rows:
                lines.append(f"• {row.get('name')}")
                lines.append(f"현재가: {row.get('current_price_fmt')}")
                if not pass_today:
                    er = str(row.get("entry_range") or "").replace("원 ~", " ~")
                    lines.append(f"볼 구간: {er}")
                check = str(row.get("agent_check_line") or "").strip()
                if pass_today:
                    lines.append("이유: 가격이 볼 구간과 너무 멀어 오늘은 패스합니다.")
                    lines.append("주의: 무리해서 따라가지 않는 편이 좋습니다.")
                else:
                    lines.append(f"이유: {row.get('ai_reason', '')}")
                    if check:
                        lines.append(check)
                    lines.append(f"주의: {row.get('ai_cancel_condition', '')}")
                lines.append("")
        else:
            lines.append("_해당 없음_")
            lines.append("")
    if scan.slack_red_overflow > 0:
        lines.append(f"_그 외 패스 {scan.slack_red_overflow}개는 JSON에 저장_")
    return "\n".join(lines).strip()


def build_scan_payload(scan: CandidateScanResult) -> dict[str, Any]:
    return {
        "version": "candidate_scan_mvp_v3_trend",
        "as_of_date": scan.as_of_date,
        "generated_at": scan.as_of_date,
        "auto_apply_watchlist": False,
        "proposal_only": True,
        "stats": {
            "pool_total": scan.pool_total,
            "pool_scan_target": scan.pool_scan_target,
            "scan_limit": scan.scan_limit,
            "scanned": scan.scanned,
            "skipped": scan.skipped,
            "excluded_watchlist": scan.excluded_watchlist,
            "excluded_large_caps": scan.excluded_large_caps,
            "excluded_preferred": scan.excluded_preferred,
            "excluded_low_tv": scan.excluded_low_tv,
            "missing_ohlcv": scan.missing_ohlcv,
            "timeout_ohlcv": scan.timeout_ohlcv,
            "candidates": len(scan.candidates),
            "green": len(scan.green),
            "yellow": len(scan.yellow),
            "red": len(scan.red),
            "slack_green": len(scan.slack_green),
            "slack_yellow": len(scan.slack_yellow),
            "slack_red": len(scan.slack_red),
            "slack_red_overflow": scan.slack_red_overflow,
            "candidate_days": scan.candidate_days,
            "daily_scan_path": scan.daily_scan_path,
        },
        "candidates": scan.candidates,
        "slack_display": {
            "green": scan.slack_green,
            "yellow": scan.slack_yellow,
            "red": scan.slack_red,
        },
        "errors": scan.errors,
    }


def write_candidate_outputs(scan: CandidateScanResult) -> Path | None:
    """data/proposals/candidate_scan/YYYY-MM-DD.json 저장."""
    if not scan.as_of_date:
        return None
    date_key = scan.as_of_date.replace("-", "")[:8]
    out_dir = SCAN_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:8]}.json"
    payload = build_scan_payload(scan)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[CANDIDATES] saved %s", path)
    return path


def validate_slack_text(text: str) -> list[str]:
    """테스트·검증용."""
    issues: list[str] = []
    if not text.strip():
        issues.append("empty")
    for word in _FORBIDDEN_SLACK:
        if word == "매수":
            if "매수" in text and "외국인 매수" not in text:
                issues.append("forbidden:매수")
        elif word in text:
            issues.append(f"forbidden:{word}")
    if re.search(r"\.{3,}|…", text):
        issues.append("ellipsis")
    return issues
