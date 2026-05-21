"""MVP 4 — 신규 후보 Slack·JSON 산출."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from agents.kr_intraday_slack.message_tone import (
    compose_new_candidate_scan_message,
    compose_new_candidate_stock_block,
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


def build_candidate_slack_text(scan: CandidateScanResult) -> str:
    """📡 오늘 새로 볼 종목 — 주간 재평가와 별도 블록."""
    clock = scan_summary_clock(scan.as_of_date)
    display = [r for r in scan.candidates if int(r.get("score") or 0) >= 35]

    if not display:
        return (
            "📡 오늘 새로 볼 종목\n\n"
            f"기준: {clock}\n"
            "오늘 새 후보 없음"
        )

    send_rows, pass_rows = candidate_rows_for_slack(scan)
    for row in send_rows + pass_rows:
        block = compose_new_candidate_stock_block(
            row,
            pass_today=row in pass_rows,
        )
        if block:
            row["slack_stock_block"] = block

    text = compose_new_candidate_scan_message(
        slot_clock=clock,
        send_rows=send_rows,
        pass_rows=pass_rows,
    )
    if _contains_forbidden(text):
        logger.warning("후보 Slack 본문에 금지어 포함 — 문구 재생성")
        text = _fallback_slack_text(scan, clock=clock)
    return text


def _fallback_slack_text(scan: CandidateScanResult, *, clock: str) -> str:
    lines = [
        "📡 오늘 새로 볼 종목",
        "",
        f"기준: {clock}",
        f"새 후보: {len(scan.green) + len(scan.yellow)}개",
        "",
    ]
    for title, rows in (
        ("🟢 지금 볼만함", scan.green),
        ("🟡 조금 기다림", scan.yellow),
        ("🔴 오늘은 패스", scan.red),
    ):
        lines.append(title)
        lines.append("")
        if rows:
            for row in rows:
                lines.append(f"• {row.get('name')}")
                lines.append(f"현재가: {row.get('current_price_fmt')}")
                if title != "🔴 오늘은 패스":
                    lines.append(f"볼 구간: {row.get('entry_range', '').replace('원 ~', ' ~')}")
                lines.append(f"이유: {build_plain_reason(row)}")
                lines.append(f"주의: {build_plain_caution(row)}")
                lines.append("")
        else:
            lines.append("_해당 없음_")
            lines.append("")
    return "\n".join(lines).strip()


def build_plain_reason(row: dict[str, Any]) -> str:
    from .candidate_scanner import build_candidate_reason

    return scrub_easy_language(build_candidate_reason(row))


def build_plain_caution(row: dict[str, Any]) -> str:
    from .candidate_scanner import build_candidate_caution

    return scrub_easy_language(build_candidate_caution(row))


def build_scan_payload(scan: CandidateScanResult) -> dict[str, Any]:
    return {
        "version": "candidate_scan_mvp_v1",
        "as_of_date": scan.as_of_date,
        "generated_at": scan.as_of_date,
        "auto_apply_watchlist": False,
        "proposal_only": True,
        "stats": {
            "scanned": scan.scanned,
            "excluded_watchlist": scan.excluded_watchlist,
            "excluded_low_tv": scan.excluded_low_tv,
            "excluded_no_data": scan.excluded_no_data,
            "candidates": len(scan.candidates),
            "green": len(scan.green),
            "yellow": len(scan.yellow),
            "red": len(scan.red),
        },
        "candidates": scan.candidates,
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
