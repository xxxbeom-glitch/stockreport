# -*- coding: utf-8
"""Mark mistaken duplicate REPLAY campaign (Firestore + local if present)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.replay.campaign_resume import mark_campaign_duplicate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duplicate-id", required=True)
    parser.add_argument("--canonical-id", required=True)
    parser.add_argument("--reason", default="duplicate_restart")
    args = parser.parse_args()
    manifest = mark_campaign_duplicate(
        args.duplicate_id,
        canonical_campaign_id=args.canonical_id,
        reason=args.reason,
    )
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
