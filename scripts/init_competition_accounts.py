# -*- coding: utf-8 -*-
"""Initialize competition team accounts (A~D) — idempotent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.bootstrap import bootstrap_competition, verify_isolation


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize AI trading competition accounts")
    parser.add_argument(
        "--verify-isolation",
        action="store_true",
        help="Print isolation check only (no writes)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without writing",
    )
    args = parser.parse_args()

    if args.verify_isolation:
        print(json.dumps(verify_isolation(), ensure_ascii=False, indent=2))
        return 0

    if args.dry_run:
        from src.trading.competition.storage.config_store import is_initialized
        from src.trading.competition.storage.accounts import accounts_exist

        print(
            json.dumps(
                {
                    "dry_run": True,
                    "already_initialized": is_initialized() and accounts_exist(),
                    "would_create_teams": ["A", "B", "C", "D"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    result = bootstrap_competition()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
