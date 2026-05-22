# -*- coding: utf-8 -*-
"""가상투자 자동운영 — 판단·체결·대기 사유를 현재 시각 기준으로 수행."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.auto_operations import run_auto_operations


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="가상투자 자동운영")
    parser.add_argument(
        "--force-judgment",
        action="store_true",
        help="대기 주문 없을 때 정기 판단 강제(테스트용)",
    )
    args = parser.parse_args()

    result = run_auto_operations(force_judgment=args.force_judgment)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
