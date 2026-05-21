"""장중 Slack 발송 로그 집계 (data/logs/kr_slack)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).resolve().parents[2] / "data" / "logs" / "kr_slack"


def _parse_day_from_record(row: dict[str, Any], fallback: date) -> date:
    logged = row.get("logged_at") or row.get("date")
    if isinstance(logged, str) and len(logged) >= 10:
        try:
            return date.fromisoformat(logged[:10])
        except ValueError:
            pass
    return fallback


def load_kr_slack_records(*, days: int = 7) -> list[dict[str, Any]]:
    """최근 N일(달력) jsonl 레코드."""
    if days < 1:
        days = 7
    end = date.today()
    start = end - timedelta(days=days - 1)
    out: list[dict[str, Any]] = []
    if not _LOG_DIR.is_dir():
        return out

    for path in sorted(_LOG_DIR.glob("*.jsonl")):
        stem = path.stem
        try:
            file_day = date.fromisoformat(stem)
        except ValueError:
            file_day = end
        if file_day < start or file_day > end:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _parse_day_from_record(row, file_day) < start:
                continue
            out.append(row)
    return out


def aggregate_ticker_slack_stats(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    ticker → {recent_slack_sent_count, recent_candidate_count, slots, last_sent_at}
    """
    stats: dict[str, dict[str, Any]] = {}
    for row in records:
        ticker = str(row.get("ticker", "")).zfill(6)
        if not ticker or not ticker.isdigit():
            continue
        bucket = stats.setdefault(
            ticker,
            {
                "recent_slack_sent_count": 0,
                "recent_candidate_count": 0,
                "slots": set(),
            },
        )
        bucket["recent_candidate_count"] += 1
        if row.get("sent") is True:
            bucket["recent_slack_sent_count"] += 1
        slot = row.get("slot")
        if slot:
            bucket["slots"].add(str(slot))
        logged = row.get("logged_at")
        if logged:
            bucket["last_sent_at"] = logged
    for ticker, bucket in stats.items():
        bucket["slots"] = sorted(bucket["slots"])
    return stats
