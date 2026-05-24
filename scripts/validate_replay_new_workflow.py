# -*- coding: utf-8
"""Guard: new-campaign workflow must never resume an existing campaign."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-type", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", default="")
    args = parser.parse_args()

    replay_type = (args.replay_type or "").strip()
    start = (args.start_date or "").strip()
    end = (args.end_date or "").strip()

    if replay_type not in ("smoke_1day", "short_5days", "month", "custom"):
        print(f"ERROR: unsupported replay_type={replay_type}", file=sys.stderr)
        return 1

    if len(start) != 8 or not start.isdigit():
        print("ERROR: start_date must be YYYYMMDD", file=sys.stderr)
        return 1

    if replay_type in ("month", "custom") and end and (len(end) != 8 or not end.isdigit()):
        print("ERROR: end_date must be YYYYMMDD when provided", file=sys.stderr)
        return 1

    print(f"OK: new campaign ({replay_type}) from {start}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
