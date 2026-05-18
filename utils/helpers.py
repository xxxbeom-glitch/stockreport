"""General helper utilities."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


def safe_json_parse(text: str) -> dict[str, Any]:
    """Parse JSON safely from plain/markdown-wrapped model output."""
    if not isinstance(text, str):
        return {}
    normalized = text.strip()
    normalized = re.sub(r"```json\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"```\s*", "", normalized)
    normalized = normalized.strip()

    try:
        parsed = json.loads(normalized)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    match = re.search(r"\{.*\}", normalized, flags=re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass

    print(f"[WARN] JSON parse failed. head={normalized[:200]!r}")
    return {}


def is_market_holiday(now: datetime | None = None) -> bool:
    """Return whether KR market is closed (weekend + managed holidays)."""
    target = now or datetime.now()
    if target.weekday() >= 5:
        return True

    # Keep this list small and explicit; update yearly as needed.
    holidays = {
        "20260101",  # 신정
        "20260216",  # 설 연휴(예시 운영값)
        "20260217",
        "20260218",
        "20260301",  # 삼일절
        "20260505",  # 어린이날
        "20260525",  # 석가탄신일(대체/예시)
        "20260606",  # 현충일
        "20260815",  # 광복절
        "20261005",  # 추석 연휴(예시 운영값)
        "20261006",
        "20261007",
        "20261009",  # 한글날
        "20261225",  # 성탄절
    }
    return target.strftime("%Y%m%d") in holidays

