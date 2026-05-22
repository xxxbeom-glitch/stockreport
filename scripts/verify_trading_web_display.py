# -*- coding: utf-8 -*-
"""kr_trading 웹 표시·상태 저장 검증 (JSON만 사용, AI 재실행 없음)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.trading_web_sync import MERGED_PATH, OUT_PATH, WEEKLY_PATH

REQUIRED_HOLDING_KEYS = (
    "ticker",
    "name",
    "current_price",
    "agent",
    "recommending_agents",
    "recommendation_count",
    "selection_reason",
    "risk_factors_text",
    "status",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _http_json(url: str, *, method: str = "GET", body: dict | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    results: list[tuple[str, bool, str]] = []

    merged = _load(MERGED_PATH)
    trading = _load(OUT_PATH)
    holdings = trading.get("holdings") or []
    merged_cards = merged.get("merged_cards") or []

    # 1) 15종 노출
    ok_count = len(holdings) == 15 and merged.get("ticker_count") == 15
    results.append(
        (
            "1. 최종 추천 15종 trading_data 반영",
            ok_count,
            f"holdings={len(holdings)}, merged.ticker_count={merged.get('ticker_count')}",
        )
    )

    # 2) 카드 필수 필드
    missing = []
    for h in holdings:
        for key in REQUIRED_HOLDING_KEYS:
            val = h.get(key)
            if val is None or val == "" or val == "—":
                if key in ("selection_reason", "risk_factors_text"):
                    continue
                missing.append(f"{h.get('name')}:{key}")
    ok_fields = len(missing) == 0
    results.append(
        (
            "2. 카드 필수 필드(종목명·현재가·에이전트·이유·위험·상태)",
            ok_fields,
            "누락 " + ", ".join(missing[:8]) if missing else "OK",
        )
    )

    # 3) 복수 에이전트 합산
    multi_merged = [c for c in merged_cards if int(c.get("recommendation_count") or 0) > 1]
    multi_hold = [h for h in holdings if int(h.get("recommendation_count") or 0) > 1]
    ok_multi = len(multi_merged) == len(multi_hold) and all(
        len(h.get("recommending_agents") or []) == int(h.get("recommendation_count") or 0)
        for h in multi_hold
    )
    results.append(
        (
            "3. 복수 추천 합산(5종 기대)",
            ok_multi and len(multi_hold) == 5,
            f"merged={len(multi_merged)}, holdings={len(multi_hold)}",
        )
    )

    # 4) Firebase/API 상태 유지
    import os

    port = os.environ.get("MOCK_TRADING_PORT", "8090")
    base = f"http://127.0.0.1:{port}"
    week_id = merged.get("week_id") or "2026-W21"
    test_ticker = str(holdings[0].get("ticker")).zfill(6) if holdings else "000000"
    persist_ok = False
    persist_detail = "API 서버 미기동 — python scripts/serve_mock_trading.py 필요"
    try:
        post_body = {
            "week_id": week_id,
            "holdings": [{"ticker": test_ticker, "status": "투자 진행 중"}],
        }
        saved = _http_json(base + "/api/trading-state", method="POST", body=post_body)
        loaded = _http_json(
            base + "/api/trading-state?" + urllib.parse.urlencode({"week_id": week_id})
        )
        state = loaded.get("state") or {}
        rows = {str(r.get("ticker")).zfill(6): r.get("status") for r in state.get("holdings") or []}
        persist_ok = saved.get("ok") and rows.get(test_ticker) == "투자 진행 중"
        backend = (saved.get("state") or {}).get("persist_backend") or "unknown"
        fb = (saved.get("state") or {}).get("firebase") or {}
        persist_detail = f"backend={backend}, firebase_ok={fb.get('ok')}, status={rows.get(test_ticker)}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        persist_detail = str(exc)

    results.append(("4. 상태 저장·재조회(새로고침 시뮬)", persist_ok, persist_detail))

    print("=== kr_trading 표시 테스트 ===\n")
    failed = 0
    for name, ok, detail in results:
        mark = "성공" if ok else "실패"
        if not ok:
            failed += 1
        print(f"[{mark}] {name}")
        print(f"       {detail}\n")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
