# -*- coding: utf-8 -*-
"""Send market-closed Slack notice when KST session is not tradable — no trading side effects."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.execution.market_session import get_session_context
from scripts.test_competition_slack import classify_webhook_url
from utils.helpers import is_market_holiday

KST = ZoneInfo("Asia/Seoul")

MARKET_CLOSED_MESSAGE = (
    "[AI 투자 경쟁앱] 현재 휴장일 또는 거래시간 외입니다.\n"
    "오늘은 시장이 열리지 않아 매수·매도 판단 및 체결을 실행하지 않습니다."
)


def market_closed_reason(at: datetime | None = None) -> tuple[bool, str]:
    """Return (is_closed, reason) for KST now or given instant."""
    now = at or datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    else:
        now = now.astimezone(KST)

    if now.weekday() >= 5:
        return True, "weekend_closed"

    if is_market_holiday(now):
        return True, "holiday"

    ctx = get_session_context(now)
    if not ctx.tradable:
        return True, ctx.label
    return False, ctx.label


def build_market_closed_payload() -> dict[str, Any]:
    return {
        "text": MARKET_CLOSED_MESSAGE,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": MARKET_CLOSED_MESSAGE,
                },
            }
        ],
    }


def send_market_closed_notice(webhook: str) -> dict[str, Any]:
    kind = classify_webhook_url(webhook)
    if kind == "workflow_trigger":
        return {
            "ok": False,
            "error": "workflow_trigger_webhook",
            "detail": (
                "SLACK_WEBHOOK_URL looks like a Slack Workflow trigger (/triggers/). "
                "Channel messages require an Incoming Webhook URL (/services/...)."
            ),
            "webhook_kind": kind,
        }

    payload_obj = build_market_closed_payload()
    payload_bytes = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook.strip(),
        data=payload_bytes,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace").strip()
            http_ok = 200 <= resp.status < 300
            slack_ok = raw_body == "ok"
            return {
                "ok": http_ok and slack_ok,
                "status": resp.status,
                "response_body": raw_body,
                "webhook_kind": kind,
                "payload_keys": list(payload_obj.keys()),
                "text_preview": MARKET_CLOSED_MESSAGE.splitlines()[0],
            }
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace").strip()
        return {
            "ok": False,
            "error": f"HTTP {exc.code}",
            "response_body": err_body,
            "webhook_kind": kind,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "webhook_kind": kind}


def main() -> int:
    closed, reason = market_closed_reason()
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z")

    if not closed:
        print(
            json.dumps(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "market_open",
                    "session_label": reason,
                    "checked_at_kst": now_kst,
                    "detail": "Market is tradable now; closed notice was not sent.",
                },
                ensure_ascii=False,
            )
        )
        return 0

    webhook = (
        os.getenv("COMPETITION_SLACK_WEBHOOK", "").strip()
        or os.getenv("SLACK_WEBHOOK_URL", "").strip()
    )
    if not webhook:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "no_webhook_configured",
                    "market_closed": True,
                    "closed_reason": reason,
                    "checked_at_kst": now_kst,
                },
                ensure_ascii=False,
            )
        )
        return 1

    result = send_market_closed_notice(webhook)
    result["market_closed"] = True
    result["closed_reason"] = reason
    result["checked_at_kst"] = now_kst
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
