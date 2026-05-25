# -*- coding: utf-8
"""Run SIMPLE_REPLAY (single-shot 5-trading-day validation)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.trading.simple_replay.runner import run_simple_replay


def main() -> int:
    p = argparse.ArgumentParser(description="SIMPLE_REPLAY — 4-agent recommendation validation")
    p.add_argument("--decision-date", required=True, help="추천 기준일 YYYYMMDD")
    p.add_argument("--observation-days", type=int, default=5)
    p.add_argument("--force", action="store_true", help="기존 완료 run 무시하고 재생성")
    p.add_argument("--no-publish", action="store_true")
    p.add_argument("--result-out", default="")
    args = p.parse_args()

    result = run_simple_replay(
        args.decision_date,
        observation_days=args.observation_days,
        force_regenerate=args.force,
        publish_pages=not args.no_publish,
    )
    out = {k: v for k, v in result.items() if k != "dashboard"}
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.result_out:
        Path(args.result_out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
