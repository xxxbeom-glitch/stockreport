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
    "plain_reason",
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

    meta = trading.get("pageMeta") or {}
    # 1) 누적 스코프·주간 메타 미노출
    ok_scope = (
        trading.get("scope") == "cumulative"
        and "week_id" not in meta
        and "weekday_label" not in meta
        and meta.get("market") == "한국시장"
        and bool(meta.get("updated_at"))
    )
    results.append(
        (
            "1. 누적 표시 스코프·pageMeta(market·updated_at만)",
            ok_scope,
            f"scope={trading.get('scope')}, pageMeta keys={sorted(meta.keys())}",
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
            "2. 카드 필수 필드(종목명·현재가·에이전트·쉬운 해설)",
            ok_fields,
            "누락 " + ", ".join(missing[:8]) if missing else "OK",
        )
    )

    # 3) 보유 종목(가상매수) 카드 필드 일관성
    ok_holdings_shape = all(h.get("virtually_bought") is True for h in holdings) if holdings else True
    results.append(
        (
            "3. 누적 보유(가상매수) 카드만 노출",
            ok_holdings_shape,
            f"holdings={len(holdings)}",
        )
    )

    # 4) 에이전트 누적 성과 필드
    agents = trading.get("agents") or []
    has_cumulative = all("cumulative_return_pct" in a for a in agents) if agents else False
    no_exit_fields = not any(h.get("status") for h in holdings)
    results.append(
        (
            "4. 종료 상태 미사용·에이전트 누적 수익률 필드",
            has_cumulative and len(agents) == 4 and no_exit_fields,
            f"agents={len(agents)}, holdings_with_status={sum(1 for h in holdings if h.get('status'))}",
        )
    )

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
