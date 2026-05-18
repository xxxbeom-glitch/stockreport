"""Slack sender helper for stock reports.

Supports:
- payload-style call: send_report(payload={...})
- direct-style call: send_report(url_or_message, summary, report_type, ...)
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime
from typing import Any

import config


def _normalize_payload(
    payload: dict[str, Any] | None,
    message: str | None,
    summary: str | None,
    report_type: str | None,
    pdf_url: str | None,
    send_at: int | None,
) -> dict[str, Any]:
    source = payload or {}
    msg = message or source.get("message") or ""
    summ = summary or source.get("summary") or ""
    rtype = report_type or source.get("report_type") or "unknown"
    url = pdf_url or source.get("pdf_url") or source.get("url") or ""
    send_ts = send_at if send_at is not None else source.get("send_at")
    return {
        "message": str(msg),
        "summary": str(summ),
        "report_type": str(rtype),
        "pdf_url": str(url),
        "send_at": send_ts,
    }


def _build_text(data: dict[str, Any]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [
        f"[{data['report_type']}] 리포트 생성 완료",
        data["summary"] or data["message"],
    ]
    if data["pdf_url"]:
        parts.append(f"링크: {data['pdf_url']}")
    parts.append(f"생성시각: {now}")
    return "\n".join(p for p in parts if p)


def _build_blocks(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Slack Block Kit payload with optional report link button."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header_text = f"[{data['report_type']}] 리포트 생성 완료"
    summary_text = data["summary"] or data["message"] or "-"
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text, "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary_text},
        },
    ]
    if data["pdf_url"]:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "리포트 보기", "emoji": True},
                        "url": data["pdf_url"],
                        "style": "primary",
                    }
                ],
            }
        )
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"생성시각: {now}"}],
        }
    )
    return blocks


def _post_webhook(webhook_url: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
        response_body = resp.read().decode("utf-8", errors="ignore")
        return {"status": resp.status, "body": response_body}


def send_report(
    payload: dict[str, Any] | None = None,
    message: str | None = None,
    summary: str | None = None,
    report_type: str | None = None,
    pdf_url: str | None = None,
    send_at: int | None = None,
) -> dict[str, Any]:
    """Send report notification to Slack webhook."""
    data = _normalize_payload(payload, message, summary, report_type, pdf_url, send_at)
    webhook_url = config.SLACK_WEBHOOK_URL or os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        return {"ok": False, "skipped": True, "reason": "SLACK_WEBHOOK_URL missing"}

    delay = 0
    if isinstance(data["send_at"], (int, float)):
        delay = int(data["send_at"] - time.time())
    if 0 < delay <= 600:
        time.sleep(delay)

    text = _build_text(data)
    blocks = _build_blocks(data)
    try:
        response = _post_webhook(webhook_url, {"text": text, "blocks": blocks})
        return {"ok": True, "response": response, "text": text, "blocks": blocks}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "text": text}
