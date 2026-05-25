"""Future-data leakage checks for SIMPLE_REPLAY."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def decision_cutoff_iso(decision_date: str) -> str:
    d = decision_date.replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}T15:30:00+09:00"


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def check_decision_leakage(decision: dict[str, Any], decision_date: str) -> dict[str, Any]:
    cutoff = _parse_ts(decision_cutoff_iso(decision_date))
    if not cutoff:
        return {"ok": False, "items": ["invalid_cutoff"]}

    items: list[str] = []
    for fact in decision.get("supporting_facts") or []:
        if not isinstance(fact, dict):
            continue
        pub = _parse_ts(str(fact.get("published_at") or ""))
        if pub and pub.astimezone(KST) > cutoff.astimezone(KST):
            items.append(str(fact.get("source_id") or fact.get("summary") or "fact"))

    ok = len(items) == 0
    decision["future_data_leakage_checked"] = True
    decision["future_data_leakage_items"] = items
    return {"ok": ok, "items": items}
