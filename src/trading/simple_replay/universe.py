"""Compact universe for SIMPLE_REPLAY (pykrx bulk first, minimal KIS)."""

from __future__ import annotations

import os
from typing import Any

from src.trading.competition.constants import MAX_ENTRY_PRICE_KRW, MIN_AVG_TRADING_VALUE_KRW
from src.trading.competition.replay.universe_replay import common_stock_records, load_static_ticker_master
from src.trading.simple_replay.constants import UNIVERSE_CAP
from src.trading.simple_replay.errors import SimpleReplayError


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = row.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _enrich_pool_pykrx_bulk(pool: list[dict[str, Any]], trading_date: str) -> int:
    """Attach close/tv/change for trading_date using 4 pykrx market OHLCV calls."""
    from src.trading.competition.replay.data_provider import list_trading_dates_result
    from src.trading.competition.replay.pykrx_safe import krx_credentials_configured, safe_pykrx_call

    if not krx_credentials_configured():
        return 0
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception:
        return 0

    cal = list_trading_dates_result(
        (trading_date[:4] + "0101"),
        trading_date,
    )
    sessions = [d for d in (cal.get("dates") or []) if d <= trading_date]
    prev_date = sessions[-2] if len(sessions) >= 2 else None
    dates = [d for d in (prev_date, trading_date) if d]

    by_date: dict[str, dict[str, dict[str, int]]] = {d: {} for d in dates}
    for date in dates:
        for market in ("KOSPI", "KOSDAQ"):
            frame, meta = safe_pykrx_call(
                f"get_market_ohlcv:{market}:{date}",
                lambda d=date, m=market: pykrx_stock.get_market_ohlcv(d, market=m),
            )
            if not meta.get("ok") or frame is None:
                continue
            for ticker, row in frame.iterrows():
                code = str(ticker).zfill(6)
                try:
                    close = int(float(row.get("종가", 0) or 0))
                    tv = int(float(row.get("거래대금", 0) or 0))
                except (TypeError, ValueError):
                    continue
                by_date[date][code] = {"close": close, "tv": tv}

    day = by_date.get(trading_date) or {}
    prev = by_date.get(prev_date or "") or {}
    enriched = 0
    for row in pool:
        code = str(row.get("ticker", "")).zfill(6)
        bar = day.get(code)
        if not bar or bar["close"] <= 0:
            continue
        row["current_price_krw"] = bar["close"]
        row["current_trading_value_krw"] = bar["tv"]
        avg_tv = float(row.get("avg_trading_value_20d_krw") or 0)
        if avg_tv > 0 and bar["tv"] > 0:
            row["tv_ratio_20d"] = bar["tv"] / avg_tv
        pbar = prev.get(code)
        if pbar and pbar["close"] > 0:
            row["change_rate_pct"] = (bar["close"] - pbar["close"]) / pbar["close"] * 100
        row.setdefault("data_sources", []).append("pykrx_bulk")
        enriched += 1
    return enriched


def load_candidate_pool(trading_date: str) -> list[dict[str, Any]]:
    """Top-liquidity common stocks with historical metrics for decision_date."""
    master = load_static_ticker_master()
    if not master:
        raise SimpleReplayError("static_universe_missing")

    rows = common_stock_records(master)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if row.get("risk_exclude_new_entry"):
            continue
        if str(row.get("security_type") or "common") != "common":
            continue
        avg_tv = int(_f(row, "avg_trading_value_20d_krw"))
        if avg_tv < MIN_AVG_TRADING_VALUE_KRW:
            continue
        price = int(_f(row, "current_price_krw") or _f(row, "last_close_krw"))
        if price > MAX_ENTRY_PRICE_KRW:
            continue
        filtered.append(dict(row))

    cap = max(40, int(os.getenv("SIMPLE_REPLAY_UNIVERSE_CAP", str(UNIVERSE_CAP))))
    filtered.sort(key=lambda r: -int(_f(r, "avg_trading_value_20d_krw")))
    pool = filtered[:cap]

    enriched = _enrich_pool_pykrx_bulk(pool, trading_date)
    min_need = max(5, min(15, len(pool) // 4))
    if enriched < min_need:
        from src.trading.competition.ops.historical_seed import enrich_universe_historical

        out = enrich_universe_historical(pool, trading_date, min_enriched=min_need)
        if not out.get("ok"):
            err = str(out.get("error") or "universe_enrich_failed")
            raise SimpleReplayError(err, detail=";".join((out.get("errors") or [])[:3]))

    priced = [r for r in pool if int(r.get("current_price_krw") or 0) > 0]
    if len(priced) < 5:
        raise SimpleReplayError("insufficient_priced_universe", detail=f"count={len(priced)}")
    return priced


def scout_candidates(pool: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    from src.trading.competition.decision.strategy_scouts import (
        scout_team_a,
        scout_team_b,
        scout_team_c,
        scout_team_d,
    )

    scouts = {
        "A": scout_team_a(pool),
        "B": scout_team_b(pool, material_tickers=set()),
        "C": scout_team_c(pool, foreign_net_fetcher=lambda _t: 0.0),
        "D": scout_team_d(pool, actionable_events=[]),
    }
    return {
        tid: [
            {
                "ticker": c.ticker,
                "name": c.name,
                "score": c.score,
                "reason_label": c.reason_label,
                "metrics": c.metrics,
                "evidence_id": f"scout:{tid}:{c.ticker}",
            }
            for c in scouts.get(tid, [])
        ]
        for tid in ("A", "B", "C", "D")
    }
