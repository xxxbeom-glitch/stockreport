# -*- coding: utf-8
"""Run one competition trading session (MVP orchestrator)."""

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

from src.trading.competition.ops.session import run_competition_session
from src.trading.competition.ops.weekly_report import build_weekly_report

KST = ZoneInfo("Asia/Seoul")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Run AI trading competition session")
    parser.add_argument("--session-id", default=datetime.now(KST).strftime("%Y%m%d_%H%M"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live-llm", action="store_true", help="Disable mock LLM provider")
    parser.add_argument("--relax-entry-filter", action="store_true")
    parser.add_argument("--weekly-report", action="store_true")
    args = parser.parse_args()

    result = run_competition_session(
        args.session_id,
        dry_run=args.dry_run,
        force_mock=not args.live_llm,
        persist_triggers=not args.dry_run,
        relax_entry_filter=args.relax_entry_filter,
    )

    if args.weekly_report:
        wr = build_weekly_report(f"week_{args.session_id[:8]}")
        result["weekly_report"] = wr

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
