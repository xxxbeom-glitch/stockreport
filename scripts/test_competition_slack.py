# -*- coding: utf-8 -*-
"""Send one Slack webhook test message — no trading, AI, or Firebase side effects."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_MESSAGE = (
    "[AI 투자 경쟁앱] Slack 연결 테스트 완료\n"
    "자동 운용 시작 전 알림 채널 연결을 확인했습니다.\n"
    "이 메시지는 테스트이며 매수·매도 또는 계좌 데이터 변경은 없습니다."
)


def classify_webhook_url(webhook: str) -> str:
    """Return incoming | workflow_trigger | unknown."""
    url = webhook.strip().lower()
    if "/services/" in url:
        return "incoming"
    if "/triggers/" in url:
        return "workflow_trigger"
    return "unknown"


def build_slack_test_payload() -> dict[str, Any]:
    """Slack Incoming Webhook body — top-level text for channel display + blocks fallback."""
    return {
        "text": TEST_MESSAGE,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": TEST_MESSAGE,
                },
            }
        ],
    }


def send_slack_test(webhook: str) -> dict[str, Any]:
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

    payload_obj = build_slack_test_payload()
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
                "text_preview": TEST_MESSAGE.splitlines()[0],
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
    webhook = (
        os.getenv("COMPETITION_SLACK_WEBHOOK", "").strip()
        or os.getenv("SLACK_WEBHOOK_URL", "").strip()
    )
    if not webhook:
        print(json.dumps({"ok": False, "error": "no_webhook_configured"}, ensure_ascii=False))
        return 1

    result = send_slack_test(webhook)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
