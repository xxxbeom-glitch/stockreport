"""오전 '오늘 매수 후보' 정량 1차 필터."""

from __future__ import annotations

from typing import Any

from agents.kr_intraday_slack.entry_price import is_chasing_price

MIN_VOL_RATIO = 0.85
MIN_TV_RATIO = 0.90
_CHASE_EXCLUDE_RATIO = 0.985


def passes_morning_quant_filter(row: dict[str, Any]) -> tuple[bool, str]:
    if not row.get("data_complete", True):
        return False, "데이터 불완전"
    vol_r = float(row.get("volume_ratio_20d") or row.get("volume_ratio") or 0)
    tv_r = float(row.get("trading_value_ratio_20d") or 0)
    if vol_r < MIN_VOL_RATIO:
        return False, "거래량 약함"
    if tv_r < MIN_TV_RATIO:
        return False, "거래대금 약함"
    foreign = float(row.get("foreign_net_eok") or 0)
    inst = float(row.get("inst_net_eok") or 0)
    if foreign <= -30 and inst <= -20:
        return False, "수급 이탈"
    current = float(row.get("current_price") or 0)
    day_high = float(row.get("day_high") or current)
    if current <= 0 or day_high <= 0:
        return False, "시세 없음"
    if is_chasing_price(row) or current / day_high >= _CHASE_EXCLUDE_RATIO:
        return False, "추격 위험"
    if not row.get("entry_range") and not row.get("entry_low"):
        return False, "진입 구간 없음"
    return True, "ok"
