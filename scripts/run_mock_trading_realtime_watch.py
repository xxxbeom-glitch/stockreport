# -*- coding: utf-8 -*-
"""실시간 감시 1회 — 시세 갱신·긴급 후보 생성 (자동 가상매수 없음)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.realtime_watch import run_watch_cycle


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="모의투자 실시간 감시")
    parser.add_argument("--min-change", type=float, default=3.0)
    parser.add_argument("--no-dart", action="store_true")
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()

    result = run_watch_cycle(
        min_change_rate=args.min_change,
        include_dart=not args.no_dart,
        persist_candidates=not args.no_persist,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
