"""EntryPriceAgent — 예약가 후보·추격 여부."""

from __future__ import annotations

from typing import Any


def _fmt_won(value: int) -> str:
    return f"{value:,}원"


def evaluate_entry(row: dict[str, Any], *, slot: str) -> dict[str, Any]:
    """종목별 판단 상태 및 예약가 범위."""
    current = int(row.get("current_price") or 0)
    day_low = int(row.get("day_low") or current)
    prev = int(row.get("prev_close") or current)
    if current <= 0:
        return {**row, "status": "데이터 부족", "is_chasing": False, "entry_range": ""}

    low_anchor = min(day_low, prev, int(current * 0.99))
    high_anchor = int((current + low_anchor) / 2)
    entry_low = max(int(low_anchor * 0.998), int(current * 0.97))
    entry_high = min(high_anchor, int(current * 0.995))
    if entry_high <= entry_low:
        entry_high = entry_low + max(100, int(current * 0.002))

    is_chasing = float(row.get("current_price") or 0) / float(row.get("day_high") or 1) >= 0.99
    vol = float(row.get("volume_ratio") or 0)
    foreign = float(row.get("foreign_net_eok") or 0)
    score = float(row.get("_pick_score") or 0)

    if is_chasing:
        status = "추격매수 위험"
    elif vol < 0.85:
        status = "거래대금 부족"
    elif foreign < -50 and vol < 1.0:
        status = "수급 약함"
    elif score >= 5.5 and not is_chasing:
        status = "진입 검토"
    elif score >= 4.5:
        status = "예약가 후보"
    elif score >= 3.5:
        status = "관찰 강화" if slot in ("1350", "1450") else "눌림 확인"
    else:
        status = "판단 애매"

    return {
        **row,
        "status": status,
        "is_chasing": is_chasing,
        "entry_range": f"{_fmt_won(entry_low)} ~ {_fmt_won(entry_high)}",
        "entry_low": entry_low,
        "entry_high": entry_high,
    }
