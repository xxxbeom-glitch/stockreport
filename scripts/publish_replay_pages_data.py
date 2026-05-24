# -*- coding: utf-8
"""Rebuild docs/replay-data public JSON from local REPLAY storage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.replay.pages_publish import (
    publish_campaign_full,
    publish_run_dashboard,
    rebuild_index,
    rebuild_pages_mirror,
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", action="append", dest="run_ids", default=[])
    parser.add_argument("--campaign", action="append", dest="campaigns", default=[])
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if args.run_ids or args.campaigns:
        if args.clean:
            rebuild_pages_mirror(clean=True)
        for rid in args.run_ids:
            publish_run_dashboard(rid)
        for cid in args.campaigns:
            publish_campaign_full(cid)
        result = {"ok": True, "index": rebuild_index()}
    else:
        result = rebuild_pages_mirror(clean=args.clean)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
