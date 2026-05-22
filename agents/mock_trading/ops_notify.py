# -*- coding: utf-8 -*-
"""가상투자 자동운영 Slack 알림 (선택)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import config
from utils.slack_destinations import is_incoming_webhook, resolve_buy_candidate_destination


def _resolve_destination() -> str:
    return (
        os.getenv("SLACK_MOCK_TRADING_WEBHOOK", "").strip()
        or os.getenv("SLACK_MOCK_TRADING_CHANNEL", "").strip()
        or resolve_buy_candidate_destination()
    )


def post_mock_trading_ops(lines: list[str], *, title: str = "가상투자 자동운영") -> dict[str, Any]:
    """운영 결과·대기 사유를 Slack으로 전송."""
    body = "\n".join(str(line) for line in lines if line)
    text = f"*{title}*\n{body}" if body else f"*{title}*"
    dest = _resolve_destination()
    if not dest:
        return {"ok": False, "skipped": True, "error": "slack_destination_not_configured"}

    if is_incoming_webhook(dest):
        payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            dest,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {"ok": 200 <= resp.status < 300, "via": "webhook"}
        except urllib.error.HTTPError as exc:
            return {"ok": False, "error": f"webhook HTTP {exc.code}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    token = (config.SLACK_BOT_TOKEN or "").strip()
    if not token:
        return {"ok": False, "skipped": True, "error": "SLACK_BOT_TOKEN missing"}

    api_payload = json.dumps(
        {"channel": dest, "text": text},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=api_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {"ok": bool(data.get("ok")), "via": "chat.postMessage", "slack": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
