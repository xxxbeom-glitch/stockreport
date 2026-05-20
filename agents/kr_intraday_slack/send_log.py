"""슬랙 발송 로그 (07_system_changes.md — 반복 발송 방지)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).resolve().parents[2] / "data" / "logs" / "kr_slack"


def _log_path(day: date | None = None) -> Path:
    d = day or date.today()
    return _LOG_DIR / f"{d.isoformat()}.jsonl"


def append_log_record(record: dict[str, Any]) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    row = {**record, "logged_at": datetime.now().isoformat(timespec="seconds")}
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_today_records() -> list[dict[str, Any]]:
    path = _log_path()
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def was_sent_today(ticker: str, *, slot: str | None = None) -> bool:
    """같은 종목 당일 슬랙 발송 여부."""
    t = str(ticker).zfill(6)
    for row in load_today_records():
        if str(row.get("ticker", "")).zfill(6) != t:
            continue
        if row.get("sent") and (slot is None or row.get("slot") == slot):
            return True
    return False


def last_sent_entry_range(ticker: str) -> str | None:
    t = str(ticker).zfill(6)
    for row in reversed(load_today_records()):
        if str(row.get("ticker", "")).zfill(6) == t and row.get("sent"):
            return str(row.get("entry_range") or "") or None
    return None


def entry_range_changed_significantly(old: str, new: str, *, threshold_pct: float = 2.0) -> bool:
    """예약가 범위가 의미 있게 바뀌었는지 (재발송 허용)."""
    if not old or not new or old == new:
        return False

    def _mid(s: str) -> float | None:
        digits = []
        for part in s.replace("원", "").replace(",", "").split("~"):
            part = part.strip()
            if part.isdigit():
                digits.append(int(part))
        if not digits:
            return None
        return sum(digits) / len(digits)

    a, b = _mid(old), _mid(new)
    if a is None or b is None or a <= 0:
        return old.strip() != new.strip()
    return abs(b - a) / a * 100.0 >= threshold_pct
