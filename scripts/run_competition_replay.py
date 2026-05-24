# -*- coding: utf-8
"""Run REPLAY smoke/campaign — isolated from LIVE accounts."""

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

os.environ.setdefault("COMPETITION_LIVE_SCHEDULE_DISABLED", "1")

from src.trading.competition.replay.campaign import run_replay_campaign  # noqa: E402
from src.trading.competition.replay.runner import run_replay_smoke  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="REPLAY run (no LIVE writes)")
    parser.add_argument(
        "--replay-type",
        default="smoke_1day",
        choices=["smoke_1day", "short_5days", "month", "full_audit", "custom"],
    )
    parser.add_argument("--date", default="20241218", help="Start trading date YYYYMMDD")
    parser.add_argument("--end-date", default="", help="End date for month/custom/full_audit")
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--no-slack", action="store_true", help="Disable Slack report links")
    parser.add_argument("--slack-dry-run", action="store_true")
    parser.add_argument("--run-audit-ai", action="store_true")
    parser.add_argument(
        "--campaign-id",
        default="",
        help="Existing campaign id (required when --resume-existing-campaign)",
    )
    parser.add_argument(
        "--resume-existing-campaign",
        action="store_true",
        help="Continue an in-progress campaign from checkpoint",
    )
    parser.add_argument(
        "--chunk-size-trading-days",
        type=int,
        default=5,
        help="Max trading days per Actions run (default 5)",
    )
    args = parser.parse_args()

    end = args.end_date.strip() or None
    os.environ["COMPETITION_EXECUTION_MODE"] = (
        "replay_audit" if args.replay_type == "full_audit" else "replay_smoke"
    )

    if args.replay_type == "smoke_1day":
        result = run_replay_smoke(
            args.date,
            force_mock=args.mock_llm,
            send_slack=False,
            run_audit_ai=args.run_audit_ai,
        )
    else:
        result = run_replay_campaign(
            args.replay_type,
            args.date,
            end,
            force_mock=args.mock_llm,
            send_slack_reports=not args.no_slack,
            slack_dry_run=args.slack_dry_run,
            run_audit_ai=args.run_audit_ai,
            campaign_id=args.campaign_id.strip() or None,
            resume_existing_campaign=args.resume_existing_campaign,
            chunk_size_trading_days=max(1, args.chunk_size_trading_days),
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
