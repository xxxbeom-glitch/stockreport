# -*- coding: utf-8 -*-
"""사업 근거 기반 산업 종목풀 생성 (AI·가격 필터 없음)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.target_sector_builder import (
    build_target_sector_universe,
    render_target_sector_review_md,
)

JSON_PATH = ROOT / "data" / "mock_trading" / "target_sector_universe.json"
REVIEW_PATH = ROOT / "data" / "mock_trading" / "target_sector_universe_review.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="산업 종목풀 (사업 근거) 생성")
    parser.add_argument(
        "--refresh-profiles",
        action="store_true",
        help="네이버 기업개요 캐시 무시 후 재수집",
    )
    parser.add_argument(
        "--max-fetch",
        type=int,
        default=0,
        help="신규 네이버 HTTP 조회 상한 (0=무제한)",
    )
    parser.add_argument(
        "--profile-delay",
        type=float,
        default=0.12,
        help="네이버 요청 간격(초)",
    )
    args = parser.parse_args()

    payload = build_target_sector_universe(
        refresh_profiles=args.refresh_profiles,
        profile_delay_sec=args.profile_delay,
        max_profile_fetch=args.max_fetch,
    )

    out = {
        "generated_at": payload["generated_at"],
        "classification_method": payload["classification_method"],
        "trading_date": payload.get("trading_date"),
        "sectors": payload["sectors"],
    }
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    REVIEW_PATH.write_text(render_target_sector_review_md(payload), encoding="utf-8")

    summary = payload.get("summary") or {}
    print(f"Wrote {JSON_PATH}")
    print(f"Wrote {REVIEW_PATH}")
    for sec in payload.get("sectors") or []:
        print(f"  {sec.get('sector_name')}: {len(sec.get('stocks') or [])} included")
    print(f"  total included: {summary.get('new_included_count')}")
    if payload.get("errors"):
        print("Errors:", payload["errors"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
