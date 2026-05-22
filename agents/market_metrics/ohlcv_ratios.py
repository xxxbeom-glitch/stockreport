"""OHLCV 이력 기반 20거래일 거래량·거래대금 비율."""

from __future__ import annotations

from typing import Any

LOOKBACK_TRADING_DAYS = 20


def ratios_from_ohlcv_rows(
    rows: list[dict[str, Any]],
    *,
    min_prior_days: int = LOOKBACK_TRADING_DAYS,
) -> dict[str, Any] | None:
    """
    마지막 행 = 기준일(오늘/최근 거래일).
    volume_ratio_20d = 당일 거래량 / 직전 20거래일 평균 거래량
    trading_value_ratio_20d = 당일 거래대금 / 직전 20거래일 평균 거래대금
    """
    if len(rows) < min_prior_days + 1:
        return None
    prior = rows[-(min_prior_days + 1) : -1]
    last = rows[-1]
    vols = [float(r.get("volume") or 0) for r in prior]
    tvs = [float(r.get("trading_value") or 0) for r in prior]
    vol_today = float(last.get("volume") or 0)
    tv_today = float(last.get("trading_value") or 0)
    vol_avg = sum(vols) / len(vols) if vols else 0.0
    tv_avg = sum(tvs) / len(tvs) if tvs else 0.0
    if vol_today <= 0 or vol_avg <= 0 or tv_today <= 0 or tv_avg <= 0:
        return None
    vol_ratio = round(vol_today / vol_avg, 2)
    tv_ratio = round(tv_today / tv_avg, 2)
    ret_5d = _return_pct(rows, 5)
    ret_20d = _return_pct(rows, 20)
    ret_60d = _return_pct(rows, min(60, len(rows) - 1))
    return {
        "volume_ratio_20d": vol_ratio,
        "trading_value_ratio_20d": tv_ratio,
        "volume_ratio": vol_ratio,
        "avg_volume_20d": vol_avg,
        "avg_trading_value_20d": tv_avg,
        "latest_trading_value": tv_today,
        "return_5d_pct": ret_5d,
        "return_20d_pct": ret_20d,
        "return_60d_pct": ret_60d,
        "overheat_5d": ret_5d is not None and ret_5d >= 15.0,
        "overheat_risk": ret_5d is not None and ret_5d >= 12.0,
    }


def _return_pct(rows: list[dict[str, Any]], days: int) -> float | None:
    if len(rows) < days + 1:
        return None
    start = float(rows[-(days + 1)].get("close") or 0)
    end = float(rows[-1].get("close") or 0)
    if start <= 0 or end <= 0:
        return None
    return round(((end / start) - 1.0) * 100.0, 2)


def attach_20d_ratio_fields(row: dict[str, Any], ratios: dict[str, Any]) -> dict[str, Any]:
    """row에 20일 비율·레거시 필드 정리."""
    out = {**row, **ratios}
    out["volume_ratio"] = ratios.get("volume_ratio_20d", out.get("volume_ratio"))
    out["trading_value_ratio_20d"] = ratios["trading_value_ratio_20d"]
    out.pop("trading_value_vs_3m", None)
    return out


def enrich_row_with_20d_ratios(
    row: dict[str, Any],
    ohlcv_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    ratios = ratios_from_ohlcv_rows(ohlcv_rows)
    if not ratios:
        return None
    return attach_20d_ratio_fields(row, ratios)


def volume_ratio_label(ratio: float | None, *, intraday: bool = False) -> str:
    if ratio is None:
        return "거래량 비교 불가"
    if intraday:
        return f"오늘 현재까지 거래량 / 최근 20일 일평균 × {ratio:.2f}"
    return f"오늘 거래량 / 최근 20일 평균 × {ratio:.2f}"


def trading_value_ratio_label(ratio: float | None, *, intraday: bool = False) -> str:
    if ratio is None:
        return "거래대금 비교 불가"
    if intraday:
        return (
            f"오늘 현재까지 거래대금 / 최근 20일 일평균 × {ratio:.2f} "
            "(장중 누적 vs 일간 평균)"
        )
    return f"오늘 거래대금 / 최근 20일 평균 × {ratio:.2f}"
