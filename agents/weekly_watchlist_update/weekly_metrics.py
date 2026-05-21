"""WeeklyMetricsAgent — 관심 25종목 주간 메트릭."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from data.kr_market import get_stock_snapshot, get_trading_date
from data.kr_watchlist import iter_watchlist_entries, watchlist_sector_labels
from data.utils import safe_float

from .slack_history import aggregate_ticker_slack_stats, load_kr_slack_records

logger = logging.getLogger("weekly_watchlist.metrics")

# 달력 lookback 단계 (거래일 10~20 확보용, 마지막 400=장기 이력)
CALENDAR_LOOKBACK_STEPS: tuple[int, ...] = (35, 55, 75)
CALENDAR_LOOKBACK_WIDE = 400
MIN_ROWS_10D = 10
MIN_ROWS_5D = 5

_OHLCV_DIAG: list[dict[str, Any]] = []

# pykrx ticker list 미포함·watchlist market 오류 보정
MARKET_HARD_OVERRIDES: dict[str, str] = {
    "010620": "KOSPI",  # HD현대미포
}


@lru_cache(maxsize=8)
def _market_ticker_set(trading_date: str, market: str) -> frozenset[str]:
    """pykrx get_market_ticker_list → zfill 티커 집합."""
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception:
        return frozenset()
    try:
        tickers = pykrx_stock.get_market_ticker_list(trading_date, market=market)
        return frozenset(str(t).zfill(6) for t in tickers)
    except Exception:
        return frozenset()


def resolve_pykrx_market(
    ticker: str,
    *,
    requested_market: str | None = None,
    trading_date: str | None = None,
) -> dict[str, Any]:
    """
    pykrx 기준 실제 시장 판별.
    KOSPI 목록 우선 → KOSDAQ → requested → 기본 KOSPI.
    """
    code = ticker.zfill(6)
    date = trading_date or get_trading_date()
    req = (requested_market or "").strip().upper()
    if req not in ("KOSPI", "KOSDAQ", "KONEX"):
        req = None

    if code in MARKET_HARD_OVERRIDES:
        return {
            "ticker": code,
            "requested_market": req,
            "resolved_market": MARKET_HARD_OVERRIDES[code],
            "resolve_source": "hard_override",
            "in_kospi": None,
            "in_kosdaq": None,
        }

    in_kospi = code in _market_ticker_set(date, "KOSPI")
    in_kosdaq = code in _market_ticker_set(date, "KOSDAQ")

    if in_kospi:
        resolved, source = "KOSPI", "pykrx_list_kospi"
    elif in_kosdaq:
        resolved, source = "KOSDAQ", "pykrx_list_kosdaq"
    elif req:
        resolved, source = req, "requested_fallback"
    else:
        resolved, source = "KOSPI", "default_kospi"

    return {
        "ticker": code,
        "requested_market": req,
        "resolved_market": resolved,
        "resolve_source": source,
        "in_kospi": in_kospi,
        "in_kosdaq": in_kosdaq,
    }


def _resolve_market(ticker: str, *, requested_market: str | None = None) -> str:
    """snapshot 등 보조 호출용."""
    return resolve_pykrx_market(ticker, requested_market=requested_market)[
        "resolved_market"
    ]


def _ohlcv_frame_to_rows(frame: Any) -> list[dict[str, Any]]:
    """pykrx DataFrame → list (empty·컬럼 불일치 시 [])."""
    if frame is None:
        return []
    try:
        if getattr(frame, "empty", False) or len(frame) < 1:
            return []
    except TypeError:
        return []

    cols = set(getattr(frame, "columns", []))
    required = {"시가", "고가", "저가", "종가", "거래량"}
    if not required.issubset(cols):
        return []

    has_tv = "거래대금" in cols
    rows: list[dict[str, Any]] = []
    for idx, row in frame.iterrows():
        close = safe_float(row.get("종가"), 0.0)
        if close <= 0:
            continue
        volume = safe_float(row.get("거래량"), 0.0)
        trading_value = (
            safe_float(row.get("거래대금"), 0.0)
            if has_tv
            else close * volume
        )
        rows.append(
            {
                "date": str(idx)[:10] if hasattr(idx, "strftime") else str(idx),
                "open": safe_float(row.get("시가"), 0.0),
                "high": safe_float(row.get("고가"), 0.0),
                "low": safe_float(row.get("저가"), 0.0),
                "close": close,
                "volume": volume,
                "trading_value": trading_value,
                "tv_source": "거래대금" if has_tv else "거래량×종가",
            }
        )
    return rows


def _call_pykrx_ohlcv_by_date(start: str, end: str, code: str) -> Any:
    """pykrx 호출 (내부 pandas INFO 억제)."""
    import logging as _logging

    from pykrx import stock as pykrx_stock  # type: ignore

    root_logger = _logging.getLogger()
    prev = root_logger.level
    try:
        root_logger.setLevel(_logging.ERROR)
        return pykrx_stock.get_market_ohlcv_by_date(start, end, code)
    finally:
        root_logger.setLevel(prev)


def _fetch_ohlcv_market_scan(
    code: str,
    *,
    end: str,
    market: str,
    calendar_days: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    by_date 실패 시 fallback: 일별 get_market_ohlcv(market)에서 ticker 행 수집.
    """
    from pykrx import stock as pykrx_stock  # type: ignore

    start_dt = datetime.strptime(end, "%Y%m%d") - timedelta(days=calendar_days)
    end_dt = datetime.strptime(end, "%Y%m%d")
    note: dict[str, Any] = {
        "method": "market_scan",
        "fallback_market": market,
        "end": end,
        "calendar_days": calendar_days,
        "ticker": code,
    }
    rows: list[dict[str, Any]] = []
    cur = start_dt
    while cur <= end_dt:
        if cur.weekday() < 5:
            d = cur.strftime("%Y%m%d")
            try:
                frame = pykrx_stock.get_market_ohlcv(d, market=market)
                if frame is None or len(frame) < 1:
                    cur += timedelta(days=1)
                    continue
                index_map = {str(i).zfill(6): i for i in frame.index}
                if code not in index_map:
                    cur += timedelta(days=1)
                    continue
                row = frame.loc[index_map[code]]
                close = safe_float(row.get("종가"), 0.0)
                if close > 0:
                    vol = safe_float(row.get("거래량"), 0.0)
                    rows.append(
                        {
                            "date": cur.strftime("%Y-%m-%d"),
                            "open": safe_float(row.get("시가"), 0.0),
                            "high": safe_float(row.get("고가"), 0.0),
                            "low": safe_float(row.get("저가"), 0.0),
                            "close": close,
                            "volume": vol,
                            "trading_value": safe_float(row.get("거래대금"), close * vol)
                            or close * vol,
                            "tv_source": "market_scan",
                        }
                    )
            except Exception:
                pass
        cur += timedelta(days=1)

    note["rows"] = len(rows)
    return rows, note


def _try_fetch_range(
    code: str,
    *,
    end: str,
    calendar_days: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """단일 기간 pykrx 조회."""
    start = (
        datetime.strptime(end, "%Y%m%d") - timedelta(days=calendar_days)
    ).strftime("%Y%m%d")
    note: dict[str, Any] = {
        "start": start,
        "end": end,
        "calendar_days": calendar_days,
        "ticker": code,
    }
    try:
        frame = _call_pykrx_ohlcv_by_date(start, end, code)
    except Exception as exc:
        note["error"] = str(exc)
        note["rows"] = 0
        return [], note

    if frame is None:
        note["rows"] = 0
        note["columns"] = []
        return [], note

    note["columns"] = list(getattr(frame, "columns", []))
    rows = _ohlcv_frame_to_rows(frame)
    note["rows"] = len(rows)
    if rows:
        note["tv_source"] = rows[-1].get("tv_source")
        note["first_date"] = rows[0]["date"]
        note["last_date"] = rows[-1]["date"]
    return rows, note


def _ohlcv_from_snapshot_hist(ticker: str, *, calendar_days: int = 60) -> list[dict[str, Any]]:
    """get_stock_snapshot과 동일 경로의 pykrx 장기 이력 (KIS 실패 시 보완)."""
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception:
        return []
    date = get_trading_date()
    start = (
        datetime.strptime(date, "%Y%m%d") - timedelta(days=calendar_days)
    ).strftime("%Y%m%d")
    code = ticker.zfill(6)
    try:
        frame = _call_pykrx_ohlcv_by_date(start, date, code)
    except Exception:
        return []
    return _ohlcv_frame_to_rows(frame)


def fetch_ohlcv_history(
    ticker: str,
    *,
    market: str | None = None,
    symbol: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    pykrx 일별 OHLCV — by_date 우선, 부족 시 KOSPI/KOSDAQ market scan fallback.
    반환: (rows, fetch_meta)
    """
    code = ticker.zfill(6)
    label = symbol or code
    end = get_trading_date()
    resolve = resolve_pykrx_market(code, requested_market=market, trading_date=end)
    resolved = resolve["resolved_market"]

    meta: dict[str, Any] = {
        "symbol": label,
        "ticker": code,
        "requested_market": resolve.get("requested_market"),
        "resolved_market": resolved,
        "resolve_source": resolve.get("resolve_source"),
        "fallback_market": None,
        "end_date": end,
        "attempts": [],
    }

    best: list[dict[str, Any]] = []

    for cal_days in CALENDAR_LOOKBACK_STEPS:
        rows, attempt = _try_fetch_range(code, end=end, calendar_days=cal_days)
        attempt["method"] = "by_date"
        meta["attempts"].append(attempt)
        if len(rows) > len(best):
            best = rows
        if len(rows) >= MIN_ROWS_10D:
            meta["selected_calendar_days"] = cal_days
            meta["row_count"] = len(rows)
            meta["rows"] = len(rows)
            logger.info(
                "[%s %s] OHLCV ok by_date rows=%d resolved_market=%s",
                label,
                code,
                len(rows),
                resolved,
            )
            return rows, meta

    for shift in (1, 2, 3):
        prev_end = (
            datetime.strptime(end, "%Y%m%d") - timedelta(days=shift)
        ).strftime("%Y%m%d")
        rows, attempt = _try_fetch_range(
            code, end=prev_end, calendar_days=CALENDAR_LOOKBACK_STEPS[-1]
        )
        attempt["method"] = "by_date"
        attempt["end_shift_days"] = shift
        meta["attempts"].append(attempt)
        if len(rows) > len(best):
            best = rows
        if len(best) >= MIN_ROWS_5D:
            meta["selected_calendar_days"] = CALENDAR_LOOKBACK_STEPS[-1]
            meta["end_shift_days"] = shift
            meta["row_count"] = len(best)
            meta["rows"] = len(best)
            return best, meta

    if len(best) < MIN_ROWS_5D:
        rows, attempt = _try_fetch_range(
            code, end=end, calendar_days=CALENDAR_LOOKBACK_WIDE
        )
        attempt["method"] = "by_date_wide"
        meta["attempts"].append(attempt)
        if len(rows) > len(best):
            best = rows
        if len(best) >= MIN_ROWS_5D:
            meta["selected_calendar_days"] = CALENDAR_LOOKBACK_WIDE
            meta["row_count"] = len(best)
            meta["rows"] = len(best)
            logger.info(
                "[%s %s] OHLCV ok by_date_wide rows=%d resolved_market=%s",
                label,
                code,
                len(best),
                resolved,
            )
            return best, meta

    if len(best) < MIN_ROWS_5D:
        for fallback_market in ("KOSPI", "KOSDAQ"):
            rows, attempt = _fetch_ohlcv_market_scan(
                code,
                end=end,
                market=fallback_market,
                calendar_days=CALENDAR_LOOKBACK_STEPS[-1],
            )
            meta["attempts"].append(attempt)
            if len(rows) > len(best):
                best = rows
                meta["fallback_market"] = fallback_market
            if len(best) >= MIN_ROWS_5D:
                meta["row_count"] = len(best)
                meta["rows"] = len(best)
                logger.info(
                    "[%s %s] OHLCV ok market_scan rows=%d resolved_market=%s fallback_market=%s",
                    label,
                    code,
                    len(best),
                    resolved,
                    fallback_market,
                )
                return best, meta

    meta["row_count"] = len(best)
    meta["rows"] = len(best)
    if best:
        meta["selected_calendar_days"] = "partial_best"
        return best, meta

    meta["failure"] = "missing_ohlcv"
    logger.warning(
        "[%s %s] OHLCV missing requested_market=%s resolved_market=%s fallback_market=%s rows=0",
        label,
        code,
        meta.get("requested_market"),
        resolved,
        meta.get("fallback_market"),
    )
    return [], meta


def classify_data_status(ohlcv_len: int) -> str:
    """5거래일 미만만 missing, 그 외 평가 가능."""
    if ohlcv_len >= MIN_ROWS_10D:
        return "ok_10d"
    if ohlcv_len >= MIN_ROWS_5D:
        return "ok_5d"
    if ohlcv_len >= 1:
        return "partial"
    return "missing_ohlcv"


def _percentile_rank(value: float, values: list[float]) -> float:
    if not values:
        return 50.0
    below = sum(1 for v in values if v < value)
    return round(100.0 * below / max(len(values) - 1, 1), 2)


def _set_data_status(row: dict[str, Any], status: str) -> None:
    row["data_quality"] = status
    row["data_status"] = status


def compute_stock_metrics(
    entry: dict[str, Any],
    ohlcv: list[dict[str, Any]],
    *,
    slack_stat: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    fetch_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ticker = str(entry.get("ticker", "")).zfill(6)
    symbol = str(entry.get("name", "")).strip()
    sector = str(entry.get("sector_name", "")).strip()

    base: dict[str, Any] = {
        "ticker": ticker,
        "symbol": symbol,
        "sector": sector,
        "ohlcv_rows": len(ohlcv),
        "last_close": None,
        "tv_5d_avg": 0,
        "tv_10d_avg": 0,
        "tv_growth_5d_vs_10d": 0.0,
        "return_5d": 0.0,
        "return_10d": 0.0,
        "drawdown_from_recent_high": 0.0,
        "position_vs_52w_high": 0.0,
        "volatility_5d": 0.0,
        "volume_ratio": None,
        "foreign_net_eok": None,
        "sector_relative_strength": 50.0,
        "recent_slack_sent_count": 0,
        "recent_candidate_count": 0,
        "data_quality": "missing_ohlcv",
        "data_status": "missing_ohlcv",
    }
    if fetch_meta:
        base["ohlcv_fetch"] = {
            "requested_market": fetch_meta.get("requested_market"),
            "resolved_market": fetch_meta.get("resolved_market"),
            "fallback_market": fetch_meta.get("fallback_market"),
            "resolve_source": fetch_meta.get("resolve_source"),
            "end_date": fetch_meta.get("end_date"),
            "row_count": fetch_meta.get("row_count") or fetch_meta.get("rows"),
            "attempts": len(fetch_meta.get("attempts") or []),
        }

    if not ohlcv:
        _set_data_status(base, "missing_ohlcv")
        if slack_stat:
            base["recent_slack_sent_count"] = int(slack_stat.get("recent_slack_sent_count") or 0)
            base["recent_candidate_count"] = int(slack_stat.get("recent_candidate_count") or 0)
        return base

    closes = [r["close"] for r in ohlcv if r["close"] > 0]
    tvs = [r["trading_value"] for r in ohlcv if r["trading_value"] > 0]
    last_close = closes[-1] if closes else 0
    base["last_close"] = int(last_close) if last_close else None

    if len(tvs) >= 5:
        base["tv_5d_avg"] = int(sum(tvs[-5:]) / 5)
    elif tvs:
        base["tv_5d_avg"] = int(sum(tvs) / len(tvs))
    if len(tvs) >= 10:
        base["tv_10d_avg"] = int(sum(tvs[-10:]) / 10)
    elif len(tvs) >= 5:
        base["tv_10d_avg"] = int(sum(tvs) / len(tvs))
    if base["tv_10d_avg"] and base["tv_5d_avg"]:
        base["tv_growth_5d_vs_10d"] = round(
            base["tv_5d_avg"] / base["tv_10d_avg"] - 1.0, 4
        )

    if len(closes) >= 6:
        base["return_5d"] = round((closes[-1] / closes[-6] - 1.0) * 100.0, 2)
    elif len(closes) >= 2:
        base["return_5d"] = round((closes[-1] / closes[0] - 1.0) * 100.0, 2)
    if len(closes) >= 11:
        base["return_10d"] = round((closes[-1] / closes[-11] - 1.0) * 100.0, 2)
    elif len(closes) >= 6:
        base["return_10d"] = round((closes[-1] / closes[-6] - 1.0) * 100.0, 2)

    window = ohlcv[-10:] if len(ohlcv) >= 10 else ohlcv
    recent_high = max((r["high"] for r in window if r["high"] > 0), default=0)
    if recent_high > 0 and last_close > 0:
        base["drawdown_from_recent_high"] = round(
            (1.0 - last_close / recent_high) * 100.0, 2
        )

    high_52 = None
    if snapshot:
        high_52 = safe_float(snapshot.get("high_52"), 0.0) or None
        if not high_52 and snapshot.get("high_52w"):
            high_52 = safe_float(snapshot["high_52w"], 0.0) or None
    if high_52 and last_close > 0:
        base["position_vs_52w_high"] = round(last_close / high_52, 4)

    last_n = ohlcv[-5:] if len(ohlcv) >= 5 else ohlcv
    ranges: list[float] = []
    for r in last_n:
        c = r["close"]
        h, lo = r["high"], r["low"]
        if c > 0 and h > 0 and lo > 0:
            ranges.append((h - lo) / c * 100.0)
    if ranges:
        base["volatility_5d"] = round(sum(ranges) / len(ranges), 2)

    if slack_stat:
        base["recent_slack_sent_count"] = int(slack_stat.get("recent_slack_sent_count") or 0)
        base["recent_candidate_count"] = int(slack_stat.get("recent_candidate_count") or 0)

    snap = snapshot or {}
    if snap.get("volume_ratio") is not None:
        base["volume_ratio"] = safe_float(snap.get("volume_ratio"), 0.0)
    if snap.get("foreign_net_eok") is not None:
        base["foreign_net_eok"] = int(snap["foreign_net_eok"])

    if not high_52 and ohlcv:
        ohlcv_high = max((r["high"] for r in ohlcv if r["high"] > 0), default=0)
        if ohlcv_high > 0 and last_close > 0:
            base["position_vs_52w_high"] = round(last_close / ohlcv_high, 4)

    _set_data_status(base, classify_data_status(len(ohlcv)))
    return base


def attach_sector_relative_strength(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """섹터 내 return_5d 기준 percentile (missing_ohlcv 제외)."""
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for row in metrics:
        by_sector.setdefault(str(row.get("sector", "")), []).append(row)

    out: list[dict[str, Any]] = []
    for _sector, group in by_sector.items():
        scored = [r for r in group if str(r.get("data_status")) != "missing_ohlcv"]
        scores = [float(r.get("return_5d") or 0.0) for r in scored]
        for row in group:
            row = dict(row)
            if str(row.get("data_status")) == "missing_ohlcv":
                row["sector_relative_strength"] = None
            else:
                row["sector_relative_strength"] = _percentile_rank(
                    float(row.get("return_5d") or 0.0), scores
                )
            out.append(row)
    order = {label: i for i, label in enumerate(watchlist_sector_labels())}

    def _sort_key(r: dict[str, Any]) -> tuple[int, str]:
        return (order.get(str(r.get("sector", "")), 99), str(r.get("ticker", "")))

    out.sort(key=_sort_key)
    return out


def _log_ohlcv_collection_summary(metrics: list[dict[str, Any]]) -> None:
    """missing_ohlcv 종목·진단 메타 요약."""
    global _OHLCV_DIAG  # noqa: PLW0603

    by_status: dict[str, list[str]] = {}
    for row in metrics:
        st = str(row.get("data_status") or "unknown")
        label = f"{row.get('symbol')}({row.get('ticker')})"
        by_status.setdefault(st, []).append(label)

    logger.info(
        "OHLCV data_status: ok_10d=%d ok_5d=%d partial=%d missing=%d",
        len(by_status.get("ok_10d", [])),
        len(by_status.get("ok_5d", [])),
        len(by_status.get("partial", [])),
        len(by_status.get("missing_ohlcv", [])),
    )

    missing = by_status.get("missing_ohlcv", [])
    if missing:
        logger.warning(
            "missing_ohlcv (%d): %s",
            len(missing),
            ", ".join(missing),
        )
        for diag in _OHLCV_DIAG:
            if diag.get("failure") == "missing_ohlcv":
                last = (diag.get("attempts") or [])[-1] if diag.get("attempts") else {}
                logger.warning(
                    "  [%s %s] requested=%s resolved=%s fallback=%s rows=%s err=%s",
                    diag.get("symbol"),
                    diag.get("ticker"),
                    diag.get("requested_market"),
                    diag.get("resolved_market"),
                    diag.get("fallback_market"),
                    diag.get("rows", 0),
                    last.get("error", ""),
                )


def collect_weekly_metrics(
    *,
    slack_log_days: int = 7,
    resolve_tickers: bool = False,
    fetch_snapshots: bool = True,
) -> list[dict[str, Any]]:
    """관심 25종목 주간 메트릭 일괄 수집."""
    global _OHLCV_DIAG  # noqa: PLW0603
    _OHLCV_DIAG = []

    slack_records = load_kr_slack_records(days=slack_log_days)
    slack_stats = aggregate_ticker_slack_stats(slack_records)
    has_slack_log = bool(slack_records)

    metrics: list[dict[str, Any]] = []
    for entry in iter_watchlist_entries(resolve_missing_tickers=resolve_tickers):
        ticker = str(entry.get("ticker", "")).zfill(6)
        if not ticker:
            logger.warning("[%s] 티커 없음 — 스킵", entry.get("name"))
            continue
        symbol = str(entry.get("name", "")).strip()
        ohlcv, fetch_meta = fetch_ohlcv_history(ticker, market=None, symbol=symbol)
        market = fetch_meta.get("resolved_market") or _resolve_market(ticker)
        fetch_meta["symbol"] = symbol

        if len(ohlcv) < MIN_ROWS_5D:
            hist = _ohlcv_from_snapshot_hist(ticker, calendar_days=75)
            if len(hist) > len(ohlcv):
                ohlcv = hist
                fetch_meta["fallback"] = "pykrx_hist_75d"
                fetch_meta["row_count"] = len(hist)

        snap: dict[str, Any] = {}
        if fetch_snapshots:
            try:
                snap = get_stock_snapshot(ticker, market=market)
                if len(ohlcv) < MIN_ROWS_5D:
                    hist2 = _ohlcv_from_snapshot_hist(ticker, calendar_days=75)
                    if len(hist2) > len(ohlcv):
                        ohlcv = hist2
                        fetch_meta["fallback"] = "kis_snapshot_hist"
            except Exception as exc:
                logger.warning("[%s %s] snapshot 실패: %s", symbol, ticker, exc)

        if len(ohlcv) < MIN_ROWS_5D:
            fetch_meta["failure"] = "missing_ohlcv"
            _OHLCV_DIAG.append(fetch_meta)
        else:
            fetch_meta.pop("failure", None)

        row = compute_stock_metrics(
            entry,
            ohlcv,
            slack_stat=slack_stats.get(ticker),
            snapshot=snap,
            fetch_meta=fetch_meta,
        )
        if not has_slack_log and row.get("data_status") in ("ok_10d", "ok_5d"):
            row["data_quality_note"] = "missing_slack_log"
        metrics.append(row)

    metrics = attach_sector_relative_strength(metrics)
    _log_ohlcv_collection_summary(metrics)
    return metrics
