"""저녁 '내일 볼 종목' 정량 1차 필터."""

from __future__ import annotations

from typing import Any

MIN_TV_RATIO = 1.05
MIN_VOL_RATIO = 1.0
MIN_TRADING_VALUE = 500_000_000
OVERHEAT_5D_EXCLUDE = 18.0


def passes_evening_quant_filter(row: dict[str, Any]) -> tuple[bool, str]:
    tv = float(row.get("latest_trading_value") or row.get("trading_value") or 0)
    if tv < MIN_TRADING_VALUE:
        return False, "거래대금 부족"
    vol_r = float(row.get("volume_ratio_20d") or row.get("volume_ratio") or 0)
    tv_r = float(row.get("trading_value_ratio_20d") or 0)
    if vol_r < MIN_VOL_RATIO:
        return False, "거래량 20일 평균 대비 미증가"
    if tv_r < MIN_TV_RATIO:
        return False, "거래대금 20일 평균 대비 미증가"
    foreign = float(row.get("foreign_net_eok") or 0)
    inst = float(row.get("inst_net_eok") or 0)
    if foreign <= 0 and inst <= 0:
        return False, "외국인·기관 수급 유입 없음"
    ret5 = float(row.get("return_5d_pct") or 0)
    if ret5 >= OVERHEAT_5D_EXCLUDE:
        return False, "단기 과열"
    return True, "ok"


def quant_risk_flags(row: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if row.get("overheat_5d") or float(row.get("return_5d_pct") or 0) >= 12.0:
        flags.append("단기 급등·과열 주의")
    if float(row.get("return_60d_pct") or 0) >= 40.0:
        flags.append("3개월 흐름 참고: 상승 폭 큼(우선 선정 아님)")
    return flags
