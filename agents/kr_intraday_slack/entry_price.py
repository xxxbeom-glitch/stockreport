"""EntryPriceAgent — 진입 후보 구간(예약가 범위) 계산."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("kr_intraday.entry_price")

# 현재가 대비 AI 허용 밴드
AI_BAND_LOW_RATIO = 0.70
AI_BAND_HIGH_RATIO = 1.02
AI_MAX_WIDTH_RATIO = 0.08
AI_NARROW_LOW_RATIO = 0.95
AI_NARROW_HIGH_RATIO = 0.99

DEFAULT_LOW_RATIO = 0.95
DEFAULT_HIGH_RATIO = 0.99


def _fmt_won(value: int) -> str:
    return f"{value:,}원"


def format_entry_range(low: int, high: int) -> str:
    if low > 0 and high > 0 and low <= high:
        return f"{_fmt_won(low)} ~ {_fmt_won(high)}"
    return ""


def _price_step(current: int) -> int:
    if current >= 200_000:
        return 500
    if current >= 50_000:
        return 100
    if current >= 10_000:
        return 50
    return 10


def _snap(price: float, current: int) -> int:
    step = _price_step(current)
    return max(step, int(round(price / step) * step))


def has_valid_entry_range(
    entry_range: str | None = None,
    *,
    entry_low: Any = None,
    entry_high: Any = None,
) -> bool:
    er = (entry_range or "").strip()
    if er and er not in ("—", "-", "N/A"):
        return True
    try:
        lo = int(entry_low) if entry_low is not None else 0
        hi = int(entry_high) if entry_high is not None else 0
        return lo > 0 and hi > 0 and lo <= hi
    except (TypeError, ValueError):
        return False


def build_entry_range_fallback(row: dict[str, Any]) -> tuple[str, int, int, str]:
    """
    AI·후보 규칙값이 없을 때 반드시 숫자 범위 생성.

    Returns (entry_range, entry_low, entry_high, source)
    source: rule_anchor | rule_default | unavailable
    """
    current = int(row.get("current_price") or 0)
    if current <= 0:
        return "", 0, 0, "unavailable"

    day_low = int(row.get("day_low") or 0)
    prev = int(row.get("prev_close") or 0)
    support = int(row.get("support_price") or 0)
    anchors = [a for a in (day_low, prev, support) if 0 < a <= current]

    if anchors:
        anchor = min(anchors)
        low = _snap(min(anchor * 0.998, current * DEFAULT_HIGH_RATIO), current)
        high = _snap(
            min(current, current * DEFAULT_HIGH_RATIO, max(anchor * 1.002, low + _price_step(current))),
            current,
        )
        high = min(high, current)
        if high <= low:
            low = _snap(current * DEFAULT_LOW_RATIO, current)
            high = _snap(current * DEFAULT_HIGH_RATIO, current)
            high = min(high, current)
        if high <= low:
            high = min(current, low + _price_step(current))
        text = format_entry_range(low, high)
        return text, low, high, "rule_anchor"

    low = _snap(current * DEFAULT_LOW_RATIO, current)
    high = _snap(current * DEFAULT_HIGH_RATIO, current)
    high = min(high, current)
    if high <= low:
        high = min(current, low + _price_step(current))
    text = format_entry_range(low, high)
    return text, low, high, "rule_default"


def normalize_ai_entry_range(
    lo: int, hi: int, current: int
) -> tuple[int, int, str]:
    """
    AI low/high 정규화.

    Returns (low, high, status)
    status: ok | cap_high | too_wide | out_of_band | invalid
    """
    if current <= 0 or lo <= 0 or hi <= 0 or lo > hi:
        return 0, 0, "invalid"

    status = "ok"
    if hi > current:
        hi = current
        status = "cap_high"

    lo_min = int(current * AI_BAND_LOW_RATIO)
    hi_max = int(current * AI_BAND_HIGH_RATIO)
    if lo < lo_min or hi > hi_max:
        return 0, 0, "out_of_band"

    if (hi - lo) > int(current * AI_MAX_WIDTH_RATIO):
        lo = _snap(current * AI_NARROW_LOW_RATIO, current)
        hi = _snap(current * AI_NARROW_HIGH_RATIO, current)
        hi = min(hi, current)
        if hi <= lo:
            hi = min(current, lo + _price_step(current))
        return lo, hi, "too_wide"

    lo = _snap(lo, current)
    hi = _snap(hi, current)
    if hi > current:
        hi = current
        status = "cap_high" if status == "ok" else status
    if hi <= lo:
        hi = min(current, lo + _price_step(current))
    return lo, hi, status


def evaluate_entry(row: dict[str, Any], *, slot: str) -> dict[str, Any]:
    """종목별 판단 상태 및 예약가 범위 (레거시·단일 패스)."""
    current = int(row.get("current_price") or 0)
    if current <= 0:
        return {**row, "status": "데이터 부족", "is_chasing": False, "entry_range": ""}

    entry_range, entry_low, entry_high, _source = build_entry_range_fallback(row)

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
        "entry_range": entry_range,
        "entry_low": entry_low,
        "entry_high": entry_high,
    }
