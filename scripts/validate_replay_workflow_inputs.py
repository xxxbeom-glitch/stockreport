# -*- coding: utf-8
"""Validate REPLAY workflow_dispatch inputs before run (prevents accidental duplicate campaigns)."""

from __future__ import annotations

import argparse
import sys


def _as_bool(value: str) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", default="false")
    parser.add_argument("--campaign-id", default="")
    args = parser.parse_args()

    resume = _as_bool(args.resume)
    cid = (args.campaign_id or "").strip()

    if resume and not cid:
        print(
            "ERROR: resume_existing_campaign=true requires campaign_id "
            "(e.g. month_20260102_20260130_1b51cb)",
            file=sys.stderr,
        )
        return 1

    if cid and not resume:
        print(
            "ERROR: campaign_id is set but resume_existing_campaign is not enabled. "
            "Refusing to start a NEW campaign. Check the resume checkbox in Actions.",
            file=sys.stderr,
        )
        return 1

    if resume and cid:
        print(f"OK: resume campaign {cid}")
    else:
        print("OK: new campaign run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
