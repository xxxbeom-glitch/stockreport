"""REPLAY Slack — weekly/monthly report links only (+ fatal errors)."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from src.trading.competition.replay.firestore_store import replay_report_url
from src.trading.competition.replay.period import FULL_AUDIT_SLACK_LABEL


def _webhook() -> str:
    return (
        os.getenv("COMPETITION_SLACK_WEBHOOK", "").strip()
        or os.getenv("SLACK_WEBHOOK_TRADING", "").strip()
        or os.getenv("SLACK_WEBHOOK_URL", "").strip()
    )


def _post_slack(payload: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "dry_run": True, "payload": payload}
    webhook = _webhook()
    if not webhook:
        return {"ok": False, "error": "no_webhook"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            return {"ok": resp.status < 300 and raw == "ok", "response_body": raw}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def send_fatal_replay_error(message: str, *, dry_run: bool = False) -> dict[str, Any]:
    text = f"[AI 투자 경쟁앱 / REPLAY 오류]\n{message}"
    return _post_slack({"text": text}, dry_run=dry_run)


def send_weekly_report_link(
    report: dict[str, Any],
    *,
    campaign_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    week_key = report.get("week_key") or report.get("report_id", "")
    label = report.get("label") or week_key
    url = report.get("url") or replay_report_url(
        campaign_id=campaign_id,
        report_key=week_key,
        report_type="weekly",
        replay_run_id=report.get("last_replay_run_id"),
    )
    text = (
        f"[{label} 주간 리포트]\n\n"
        f"박성범님, {label} AI 투자 에이전트의 REPLAY 주간 실적 리포트입니다.\n"
        f"(REPLAY 테스트 — LIVE 성과 미반영)\n\n"
        f"<{url}|웹에서 리포트 확인하기>"
    )
    payload = {
        "text": text,
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "웹에서 리포트 확인하기"},
                        "url": url,
                    }
                ],
            },
        ],
    }
    return _post_slack(payload, dry_run=dry_run)


def send_monthly_report_link(
    report: dict[str, Any],
    *,
    campaign_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    month_key = report.get("month_key") or report.get("report_id", "")
    label = report.get("label") or month_key
    url = report.get("url") or replay_report_url(
        campaign_id=campaign_id,
        report_key=month_key,
        report_type="monthly",
        replay_run_id=report.get("last_replay_run_id"),
    )
    text = (
        f"[{label} 월간 리포트]\n\n"
        f"박성범님, {label} AI 투자 에이전트의 REPLAY 월간 실적 리포트입니다.\n"
        f"(REPLAY 테스트 — LIVE 성과 미반영)\n\n"
        f"<{url}|웹에서 월간 리포트 확인하기>"
    )
    payload = {
        "text": text,
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "웹에서 월간 리포트 확인하기"},
                        "url": url,
                    }
                ],
            },
        ],
    }
    return _post_slack(payload, dry_run=dry_run)


def send_final_report_link(
    report: dict[str, Any],
    *,
    campaign_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    label = report.get("label") or FULL_AUDIT_SLACK_LABEL
    url = report.get("url") or replay_report_url(
        campaign_id=campaign_id,
        report_key="final",
        report_type="final",
        replay_run_id=report.get("last_replay_run_id"),
    )
    text = (
        f"[{label}]\n\n"
        f"박성범님, AI 투자 에이전트의 리플레이 투자대결이 종료되었습니다.\n"
        f"최종 실적과 감사 결과를 확인해 주세요.\n\n"
        f"(REPLAY 테스트 — LIVE 성과 미반영)"
    )
    payload = {
        "text": text,
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "최종 리포트 확인하기"},
                        "url": url,
                    }
                ],
            },
        ],
    }
    return _post_slack(payload, dry_run=dry_run)
