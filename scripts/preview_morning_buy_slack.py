#!/usr/bin/env python3
"""매수 후보 Slack 미리보기 (발송 없음)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.kr_intraday_slack.entry_price import enrich_intraday_entry  # noqa: E402
from agents.morning_buy.slack_message import build_morning_buy_slack_bundle  # noqa: E402


def _row(name: str, ticker: str, price: int, foreign: float) -> dict:
    return enrich_intraday_entry(
        {
            "name": name,
            "ticker": ticker,
            "current_price": price,
            "current_price_fmt": f"{price:,}원",
            "day_high": int(price * 1.02),
            "volume_ratio_20d": 1.09,
            "trading_value_ratio_20d": 1.17,
            "foreign_net_eok": foreign,
            "inst_net_eok": 0,
            "ai_decision": "진입 검토",
            "ai_reason": "평소보다 거래가 늘고 있어 관심이 들어오는 중임.",
            "ai_cancel_condition": "거래 급감 시 오늘은 넘기기",
        },
        slot="1025",
    )


def main() -> int:
    rows = [
        _row("하나마이크론", "067310", 81200, -17),
        _row("테스트반도체", "000001", 45200, 5),
    ]
    bundle = build_morning_buy_slack_bundle(slot="1025", send_rows=rows, scanned=25)
    for i, msg in enumerate(bundle["messages"], start=1):
        print(f"--- MESSAGE {i} ---")
        print(msg)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
