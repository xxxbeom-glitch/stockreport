# -*- coding: utf-8
"""Select the single resumable REPLAY campaign for Actions resume workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.replay.campaign_select import (  # noqa: E402
    format_selection_banner,
    select_unique_resumable_campaign,
)


def _append_github_output(key: str, value: str) -> None:
    out_path = os.getenv("GITHUB_OUTPUT")
    if not out_path:
        return
    with open(out_path, "a", encoding="utf-8") as f:
        safe = value.replace("\n", " ")
        f.write(f"{key}={safe}\n")


def _append_step_summary(lines: list[str]) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    p = Path(summary_path)
    existing = p.read_text(encoding="utf-8") if p.is_file() else ""
    p.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-days", type=int, default=5)
    parser.add_argument("--json-out", default="", help="Write full selection JSON to path")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()

    result = select_unique_resumable_campaign()
    banner = format_selection_banner(result, chunk_days=args.chunk_days)
    _append_step_summary(banner)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.github_output and result.get("ok"):
        _append_github_output("campaign_id", str(result.get("campaign_id") or ""))
        _append_github_output("replay_type", str(result.get("replay_type") or "month"))
        _append_github_output("start_date", str(result.get("start_date") or ""))
        _append_github_output("end_date", str(result.get("end_date") or ""))
        _append_github_output("next_trading_date", str(result.get("next_trading_date") or ""))

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("ok"):
        print(result.get("error"), file=sys.stderr)
        return 1

    cid = result.get("campaign_id")
    print(f"Selected resumable campaign: {cid}")
    print(f"Next trading date: {result.get('next_trading_date')}")
    print(f"Chunk days: {args.chunk_days}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
