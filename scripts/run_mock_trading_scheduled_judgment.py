# -*- coding: utf-8 -*-
"""정기 AI 판단 (월·목·금 15:30 이후) — 신규 가상매수 대기열 등록."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.scheduled_judgment import run_scheduled_judgment


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="정기 AI 가상매수 판단")
    parser.add_argument(
        "--entry-type",
        choices=["REGULAR_MON", "REGULAR_THU", "REGULAR_FRI_WEEKEND"],
        default=None,
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="15:30 이전·비판단일도 실행")
    args = parser.parse_args()

    result = run_scheduled_judgment(
        entry_type=args.entry_type,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
