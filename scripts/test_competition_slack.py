# -*- coding: utf-8 -*-
"""Send one Slack webhook test message — no trading, AI, or Firebase side effects."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_MESSAGE = (
    "[AI 투자 경쟁앱] Slack 연결 테스트 완료\n"
    "자동 운용 시작 전 알림 채널 연결을 확인했습니다.\n"
    "이 메시지는 테스트이며 매수·매도 또는 계좌 데이터 변경은 없습니다."
)


def main() -> int:
    webhook = (
        os.getenv("COMPETITION_SLACK_WEBHOOK", "").strip()
        or os.getenv("SLACK_WEBHOOK_URL", "").strip()
    )
    if not webhook:
        print(json.dumps({"ok": False, "error": "no_webhook_configured"}, ensure_ascii=False))
        return 1

    payload = json.dumps({"text": TEST_MESSAGE}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            print(json.dumps({"ok": ok, "status": resp.status}, ensure_ascii=False))
            return 0 if ok else 1
    except urllib.error.HTTPError as exc:
        print(json.dumps({"ok": False, "error": f"HTTP {exc.code}"}, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
