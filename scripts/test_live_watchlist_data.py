#!/usr/bin/env python3
"""KIS/pykrx 라이브 수집 스모크 테스트 (1종목 → 전체)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.kr_intraday_slack.market_data import collect_watchlist_market_data
from data.kr_watchlist import watchlist_stock_count


def _print_row(row: dict) -> None:
    print(f"--- {row.get('ticker')} {row.get('name')} ---")
    print(f"  data_complete={row.get('data_complete')} source={row.get('price_source')}")
    print(f"  current={row.get('current_price_fmt')} prev_close={row.get('prev_close')}")
    print(f"  day_high={row.get('day_high')} day_low={row.get('day_low')}")
    print(f"  trading_value={row.get('trading_value_fmt')}")
    print(f"  volume_ratio={row.get('volume_ratio')} foreign_eok={row.get('foreign_net_eok')} inst_eok={row.get('inst_net_eok')}")
    for err in row.get("fetch_errors") or []:
        print(f"  ERROR: {err}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="089030", help="단일 종목 티커 (기본: 테크윙)")
    parser.add_argument("--all", action="store_true", help="관심종목 전체 25개")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    tickers = None if args.all else [str(args.ticker).zfill(6)]
    rows = collect_watchlist_market_data("0930", live=True, tickers=tickers)
    ok = sum(1 for r in rows if r.get("data_complete"))
    print(f"\n[SUMMARY] fetched={len(rows)} ok={ok} fail={len(rows)-ok} expected={watchlist_stock_count() if args.all else 1}")
    for row in rows:
        _print_row(row)
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
