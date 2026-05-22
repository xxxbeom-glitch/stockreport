# -*- coding: utf-8 -*-
"""가상 지정가 주문 체결/미체결 판정 (NXT 16:00~18:00 / KRX 09:10~15:30)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.virtual_buy_executor import process_limit_orders


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    result = process_limit_orders()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
