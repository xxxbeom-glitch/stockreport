# -*- coding: utf-8 -*-
"""Run competition event detection + shared analyzer routing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.events.pipeline import run_event_scan


def main() -> int:
    parser = argparse.ArgumentParser(description="Competition event scan (Phase 3)")
    parser.add_argument("--position-only", action="store_true", help="Scan holdings only")
    parser.add_argument("--eligible-only", action="store_true", help="Scan eligible universe only")
    parser.add_argument(
        "--max-eligible",
        type=int,
        default=0,
        help="Limit eligible ticker scan (0=all)",
    )
    parser.add_argument("--no-dart", action="store_true")
    parser.add_argument("--no-news", action="store_true")
    parser.add_argument("--no-market", action="store_true")
    parser.add_argument("--gemini", action="store_true", help="Use Gemini event analyzer")
    parser.add_argument("--dry-run", action="store_true", help="Detect only, no persist")
    args = parser.parse_args()

    scan_eligible = not args.position_only
    scan_positions = not args.eligible_only

    if args.dry_run:
        from src.trading.competition.events.pipeline import build_eligible_map, build_position_watch_map
        from src.trading.competition.events.detector import scan_ticker

        pos = build_position_watch_map()
        elig = build_eligible_map()
        tickers = list(elig.keys())[: args.max_eligible or len(elig)]
        signals = []
        for t, info in pos.items():
            signals.extend(
                scan_ticker(
                    t,
                    info.get("name", t),
                    scope="position_holding",
                    holding_teams=info.get("holding_teams", []),
                )
            )
        for t in tickers:
            meta = elig[t]
            signals.extend(
                scan_ticker(
                    t,
                    meta.get("name", t),
                    scope="eligible_candidate",
                    stock_meta=meta,
                )
            )
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "position_tickers": len(pos),
                    "eligible_tickers": len(tickers),
                    "signals_detected": len(signals),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    result = run_event_scan(
        scan_eligible=scan_eligible,
        scan_positions=scan_positions,
        max_eligible_tickers=args.max_eligible,
        include_dart=not args.no_dart,
        include_news=not args.no_news,
        include_market=not args.no_market,
        use_gemini_analyzer=args.gemini,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
