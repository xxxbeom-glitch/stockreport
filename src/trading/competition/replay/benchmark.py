"""KOSPI/KOSDAQ weighted benchmark for REPLAY final report."""

from __future__ import annotations

from contextlib import redirect_stderr
import io
from typing import Any

from src.trading.competition.replay.period import FULL_AUDIT_END, FULL_AUDIT_START

# pykrx index tickers (KOSPI composite, KOSDAQ composite)
_INDEX_KOSPI = "1001"
_INDEX_KOSDAQ = "2001"
_WEIGHT_KOSPI = 0.6
_WEIGHT_KOSDAQ = 0.4


def _pykrx():
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        return pykrx_stock
    except Exception:
        return None


def _index_return_pct(index_code: str, start: str, end: str) -> tuple[float | None, str | None]:
    pykrx = _pykrx()
    if pykrx is None:
        return None, "pykrx_unavailable"
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            frame = pykrx.get_index_ohlcv_by_date(start, end, index_code)
        if frame is None or len(frame) < 2:
            return None, "index_ohlcv_insufficient"
        first = float(frame["종가"].iloc[0])
        last = float(frame["종가"].iloc[-1])
        if first <= 0:
            return None, "index_start_invalid"
        return round((last - first) / first * 100, 2), None
    except Exception as exc:
        return None, f"{type(exc).__name__}:{exc}"


def compute_weighted_benchmark(
    start: str = FULL_AUDIT_START,
    end: str = FULL_AUDIT_END,
) -> dict[str, Any]:
    kospi, kospi_err = _index_return_pct(_INDEX_KOSPI, start, end)
    kosdaq, kosdaq_err = _index_return_pct(_INDEX_KOSDAQ, start, end)

    if kospi is not None and kosdaq is not None:
        blended = round(kospi * _WEIGHT_KOSPI + kosdaq * _WEIGHT_KOSDAQ, 2)
        verified = True
        note = None
    else:
        blended = None
        verified = False
        note = "벤치마크 OHLCV 조회 실패 — KRX 로그인 또는 네트워크 확인 필요"

    return {
        "period_start": start,
        "period_end": end,
        "weights": {"KOSPI": _WEIGHT_KOSPI, "KOSDAQ": _WEIGHT_KOSDAQ},
        "kospi_return_pct": kospi,
        "kosdaq_return_pct": kosdaq,
        "blended_return_pct": blended,
        "verified": verified,
        "errors": {"kospi": kospi_err, "kosdaq": kosdaq_err},
        "note": note,
    }


def team_vs_benchmark(team_return_pct: float, benchmark: dict[str, Any]) -> dict[str, Any]:
    blended = benchmark.get("blended_return_pct")
    if blended is None:
        return {"alpha_pct": None, "vs_blended": "unverified"}
    alpha = round(team_return_pct - float(blended), 2)
    return {"alpha_pct": alpha, "vs_blended": "outperform" if alpha > 0 else ("underperform" if alpha < 0 else "inline")}
