# -*- coding: utf-8
"""Run REPLAY smoke/audit — isolated from LIVE accounts."""

from __future__ import annotations

import argparse
import json
import os
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

import config  # noqa: F401

_MODEL_DEFAULTS = {
    "COMPETITION_A_MAIN_MODEL": "deepseek-v4-flash",
    "COMPETITION_A_PARTNER_MODEL": "gemini-2.5-flash-lite",
    "COMPETITION_B_MAIN_MODEL": "gemini-2.5-flash-lite",
    "COMPETITION_B_PARTNER_MODEL": "deepseek-v4-flash",
    "COMPETITION_C_MAIN_MODEL": "deepseek-v4-flash",
    "COMPETITION_C_VALIDATOR_MODEL": "gemini-2.5-flash-lite",
    "COMPETITION_D_MAIN_MODEL": "gemini-2.5-flash-lite",
    "COMPETITION_D_VALIDATOR_MODEL": "deepseek-v4-pro",
}
for _k, _v in _MODEL_DEFAULTS.items():
    os.environ.setdefault(_k, _v)

os.environ.setdefault("COMPETITION_EXECUTION_MODE", "replay_smoke")
os.environ.setdefault("COMPETITION_LIVE_SCHEDULE_DISABLED", "1")

from src.trading.competition.replay.runner import run_replay_smoke  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="REPLAY smoke run (no LIVE writes)")
    parser.add_argument("--date", default="20260522", help="Decision trading date YYYYMMDD")
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--no-slack", action="store_true")
    parser.add_argument("--slack-dry-run", action="store_true")
    parser.add_argument("--run-audit-ai", action="store_true")
    args = parser.parse_args()

    result = run_replay_smoke(
        args.date,
        force_mock=args.mock_llm,
        send_slack=not args.no_slack,
        slack_dry_run=args.slack_dry_run,
        run_audit_ai=args.run_audit_ai,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
