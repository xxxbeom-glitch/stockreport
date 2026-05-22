# -*- coding: utf-8 -*-
"""merged_recommendations + weekly_recommendations → trading_data.json (AI 재실행 없음)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.trading_web_sync import (
    MERGED_PATH,
    OUT_PATH,
    WEEKLY_PATH,
    build_trading_data,
)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not MERGED_PATH.is_file():
        print(f"실패: {MERGED_PATH} 없음")
        return 1
    if not WEEKLY_PATH.is_file():
        print(f"실패: {WEEKLY_PATH} 없음")
        return 1

    payload = build_trading_data()
    n = len(payload.get("holdings") or [])
    multi = sum(
        1 for h in payload.get("holdings") or [] if int(h.get("recommendation_count") or 0) > 1
    )
    print(f"week_id={payload.get('pageMeta', {}).get('week_id')} holdings={n}종")
    print(f"복수 추천 종목: {multi}종")
    print(f"저장: {OUT_PATH}")
    return 0 if n == 15 else 1


if __name__ == "__main__":
    raise SystemExit(main())
