"""Slack notifications — dry-run payload for verification."""

from __future__ import annotations

import json
import os
from typing import Any


def build_slack_payload(
    event_type: str,
    *,
    title: str,
    body: str,
    team_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured payload (no secrets). Used for dry-run verification."""
    return {
        "channel": "competition-ops",
        "event_type": event_type,
        "title": title,
        "body": body,
        "team_id": team_id,
        "metadata": metadata or {},
        "dry_run": os.getenv("COMPETITION_SLACK_DRY_RUN", "").lower() in ("1", "true", "yes")
        or not (os.getenv("COMPETITION_SLACK_WEBHOOK") or os.getenv("SLACK_WEBHOOK_URL")),
    }


def send_competition_slack(message: str, *, level: str = "info", dry_run: bool = False, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    structured = payload or build_slack_payload(level, title=level, body=message)
    if dry_run or structured.get("dry_run"):
        return {"ok": True, "dry_run": True, "payload": structured}

    webhook = os.getenv("COMPETITION_SLACK_WEBHOOK") or os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        return {"ok": False, "error": "no_webhook_configured", "payload": structured}

    try:
        import urllib.request

        text = structured.get("body") or message
        body = json.dumps({"text": f"[competition/{level}] {text}"}).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": resp.status < 300, "status": resp.status, "payload": structured}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "payload": structured}


def notify_trade(trade: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    payload = build_slack_payload(
        "trade_fill",
        title=f"팀 {trade.get('team_id')} 체결",
        body=f"{trade.get('name')} {trade.get('quantity')}주 @ {int(trade.get('fill_price_krw', 0)):,}원",
        team_id=trade.get("team_id"),
        metadata={"trade_id": trade.get("trade_id"), "side": trade.get("side")},
    )
    return send_competition_slack(payload["body"], level="trade", dry_run=dry_run, payload=payload)
