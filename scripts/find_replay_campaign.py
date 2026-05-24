# -*- coding: utf-8
"""List REPLAY campaigns (local manifest + optional Firestore) for resume."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.replay.campaign_resume import CAMPAIGNS_ROOT, list_resumable_campaigns


def _local_campaigns() -> list[dict]:
    rows: list[dict] = []
    if not CAMPAIGNS_ROOT.is_dir():
        return rows
    for manifest_path in sorted(CAMPAIGNS_ROOT.glob("*/manifest.json")):
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "source": "local",
                "campaign_id": m.get("campaign_id") or manifest_path.parent.name,
                "replay_type": m.get("replay_type"),
                "days_completed": m.get("days_completed"),
                "days_total": m.get("days_total"),
                "next_trading_date": m.get("next_trading_date"),
                "needs_resume": m.get("needs_resume"),
                "competition_status": m.get("competition_status"),
                "progress_label": m.get("progress_label"),
                "completed_trading_dates": m.get("completed_trading_dates"),
            }
        )
    return rows


def _firestore_campaigns() -> list[dict]:
    try:
        from src.trading.competition.constants import COLLECTION_REPLAY_CAMPAIGNS
        from src.trading.competition.storage.base import firestore_client

        client, status = firestore_client()
        if not client:
            return [{"source": "firestore", "error": status.get("error", "unavailable")}]
        rows: list[dict] = []
        for doc in client.collection(COLLECTION_REPLAY_CAMPAIGNS).stream():
            m = doc.to_dict() or {}
            rows.append(
                {
                    "source": "firestore",
                    "campaign_id": m.get("campaign_id") or doc.id,
                    "replay_type": m.get("replay_type"),
                    "days_completed": m.get("days_completed"),
                    "days_total": m.get("days_total"),
                    "next_trading_date": m.get("next_trading_date"),
                    "needs_resume": m.get("needs_resume"),
                    "competition_status": m.get("competition_status"),
                    "progress_label": m.get("progress_label"),
                }
            )
        return rows
    except Exception as exc:
        return [{"source": "firestore", "error": type(exc).__name__}]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--days-completed", type=int, default=0)
    parser.add_argument("--days-total", type=int, default=0)
    parser.add_argument("--next-trading-date", default="")
    parser.add_argument("--replay-type", default="")
    args = parser.parse_args()

    rows = _local_campaigns() + _firestore_campaigns()
    if args.replay_type:
        rows = [r for r in rows if r.get("replay_type") == args.replay_type]
    if args.days_completed:
        rows = [r for r in rows if r.get("days_completed") == args.days_completed]
    if args.days_total:
        rows = [r for r in rows if r.get("days_total") == args.days_total]
    if args.next_trading_date:
        rows = [r for r in rows if r.get("next_trading_date") == args.next_trading_date]

    print(json.dumps({"campaigns": rows, "resumable": list_resumable_campaigns()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
