# -*- coding: utf-8
"""Build Phase 4 decision triggers for a trading session."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.decision.pipeline import run_trigger_build

KST = ZoneInfo("Asia/Seoul")


def _default_session_id() -> str:
    return datetime.now(KST).strftime("%Y%m%d_%H%M")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase 4 decision triggers")
    parser.add_argument("--session-id", default=_default_session_id())
    parser.add_argument("--no-strategy", action="store_true")
    parser.add_argument("--no-actionable", action="store_true")
    parser.add_argument("--no-position", action="store_true")
    parser.add_argument("--no-market-enrich", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build triggers without persisting",
    )
    args = parser.parse_args()

    if args.dry_run:
        from src.trading.competition.decision.triggers import build_all_decision_triggers

        triggers = build_all_decision_triggers(
            args.session_id,
            include_strategy=not args.no_strategy,
            include_actionable=not args.no_actionable,
            include_position=not args.no_position,
            enrich_market=not args.no_market_enrich,
        )
        from collections import Counter

        print(
            json.dumps(
                {
                    "dry_run": True,
                    "session_id": args.session_id,
                    "trigger_total": len(triggers),
                    "by_type": dict(Counter(t.trigger_type for t in triggers)),
                    "by_team": dict(Counter(t.team_id for t in triggers)),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    result = run_trigger_build(
        args.session_id,
        include_strategy=not args.no_strategy,
        include_actionable=not args.no_actionable,
        include_position=not args.no_position,
        enrich_market=not args.no_market_enrich,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
