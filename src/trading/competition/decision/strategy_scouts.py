"""Team-specific strategy candidate scouts from eligible universe."""

from __future__ import annotations

from typing import Any, Callable

from src.trading.competition.constants import MAX_CANDIDATES
from src.trading.competition.decision.d_scout import (
    collect_blocked_d_tickers,
    evaluate_d_candidate,
)
from src.trading.competition.decision.models import StrategyCandidate
from src.trading.competition.universe.builder import load_eligible_universe

# Team A — breakout / volume
A_MIN_TV_RATIO = 1.5
A_MIN_CHANGE_PCT = 2.0

# Team C — supply / liquidity persistence
C_MIN_AVG_TV = 5_000_000_000

# Team D — pullback / rebound (see d_scout.py for filters)


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = row.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _change_rate(row: dict[str, Any]) -> float:
    if row.get("change_rate_pct") is not None:
        return _f(row, "change_rate_pct")
    metrics = row.get("metrics") or {}
    return _f(metrics, "change_rate_pct")


def _tv_ratio(row: dict[str, Any]) -> float:
    if row.get("tv_ratio_20d") is not None:
        return _f(row, "tv_ratio_20d")
    avg = _f(row, "avg_trading_value_20d_krw")
    cur = _f(row, "current_trading_value_krw")
    if avg > 0 and cur > 0:
        return cur / avg
    return 0.0


def scout_team_a(stocks: list[dict[str, Any]]) -> list[StrategyCandidate]:
    """거래대금 급증·가격 돌파·단기 강도."""
    scored: list[StrategyCandidate] = []
    for row in stocks:
        ticker = str(row.get("ticker", "")).zfill(6)
        change = _change_rate(row)
        tv_r = _tv_ratio(row)
        if tv_r < A_MIN_TV_RATIO and change < A_MIN_CHANGE_PCT:
            continue
        score = tv_r * 10 + max(0, change)
        reasons = []
        if tv_r >= A_MIN_TV_RATIO:
            reasons.append(f"tv_ratio_{tv_r:.1f}x")
        if change >= A_MIN_CHANGE_PCT:
            reasons.append(f"change_{change:+.1f}%")
        scored.append(
            StrategyCandidate(
                ticker=ticker,
                name=str(row.get("name") or ticker),
                score=score,
                reason_label="+".join(reasons) or "momentum",
                metrics={
                    "tv_ratio_20d": tv_r,
                    "change_rate_pct": change,
                    "current_price_krw": row.get("current_price_krw"),
                },
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[: MAX_CANDIDATES["A"]]


def scout_team_b(
    stocks: list[dict[str, Any]],
    *,
    material_tickers: set[str] | None = None,
) -> list[StrategyCandidate]:
    """공시·재료 — universe 중 material 이벤트 연결 또는 유동성 상위."""
    material_tickers = material_tickers or set()
    scored: list[StrategyCandidate] = []
    for row in stocks:
        ticker = str(row.get("ticker", "")).zfill(6)
        avg_tv = _f(row, "avg_trading_value_20d_krw")
        has_material = ticker in material_tickers
        if not has_material and avg_tv < C_MIN_AVG_TV:
            continue
        score = (100.0 if has_material else 0.0) + avg_tv / 1_000_000_000
        scored.append(
            StrategyCandidate(
                ticker=ticker,
                name=str(row.get("name") or ticker),
                score=score,
                reason_label="material_linked" if has_material else "liquidity_watch",
                metrics={"avg_trading_value_20d_krw": int(avg_tv)},
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[: MAX_CANDIDATES["B"]]


def scout_team_c(
    stocks: list[dict[str, Any]],
    *,
    foreign_net_fetcher: Callable[[str], float | None] | None = None,
) -> list[StrategyCandidate]:
    """수급·거래대금 지속성 — 유동성 + 외국인 순매수(가능 시)."""
    pool = sorted(
        stocks,
        key=lambda r: _f(r, "avg_trading_value_20d_krw"),
        reverse=True,
    )[:80]

    scored: list[StrategyCandidate] = []
    for row in pool:
        ticker = str(row.get("ticker", "")).zfill(6)
        avg_tv = _f(row, "avg_trading_value_20d_krw")
        if avg_tv < C_MIN_AVG_TV:
            continue
        foreign = None
        if foreign_net_fetcher:
            try:
                foreign = foreign_net_fetcher(ticker)
            except Exception:
                foreign = None
        if foreign is None:
            try:
                from data.kr_market import get_foreign_net_by_ticker

                foreign = get_foreign_net_by_ticker(ticker)
            except Exception:
                foreign = 0.0

        score = avg_tv / 1_000_000_000 + (foreign or 0) / 100_000_000
        scored.append(
            StrategyCandidate(
                ticker=ticker,
                name=str(row.get("name") or ticker),
                score=score,
                reason_label="supply_persistence",
                metrics={
                    "avg_trading_value_20d_krw": int(avg_tv),
                    "foreign_net": foreign,
                },
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[: MAX_CANDIDATES["C"]]


def scout_team_d(
    stocks: list[dict[str, Any]],
    *,
    blocked_tickers: set[str] | None = None,
    actionable_events: list[dict[str, Any]] | None = None,
) -> list[StrategyCandidate]:
    """눌림 후 안정화·반등 초기 신호 + 유동성/수급 회복 + 위험 제외."""
    blocked = set(blocked_tickers or set())
    blocked |= collect_blocked_d_tickers(actionable_events)

    scored: list[StrategyCandidate] = []
    for row in stocks:
        ok, reject_reason, rebound_signals = evaluate_d_candidate(
            row, blocked_tickers=blocked
        )
        if not ok:
            continue
        ticker = str(row.get("ticker", "")).zfill(6)
        change = _change_rate(row)
        avg_tv = _f(row, "avg_trading_value_20d_krw")
        tv_r = _tv_ratio(row)
        score = len(rebound_signals) * 10 + abs(change) + tv_r * 5
        scored.append(
            StrategyCandidate(
                ticker=ticker,
                name=str(row.get("name") or ticker),
                score=score,
                reason_label="+".join(rebound_signals) or "rebound_setup",
                metrics={
                    "change_rate_pct": change,
                    "avg_trading_value_20d_krw": int(avg_tv),
                    "tv_ratio_20d": tv_r,
                    "rebound_signals": rebound_signals,
                    "reject_reason_avoided": reject_reason,
                },
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[: MAX_CANDIDATES["D"]]


def scout_all_teams(
    *,
    material_tickers: set[str] | None = None,
    universe: list[dict[str, Any]] | None = None,
    actionable_events: list[dict[str, Any]] | None = None,
) -> dict[str, list[StrategyCandidate]]:
    stocks = universe if universe is not None else load_eligible_universe()
    return {
        "A": scout_team_a(stocks),
        "B": scout_team_b(stocks, material_tickers=material_tickers),
        "C": scout_team_c(stocks),
        "D": scout_team_d(stocks, actionable_events=actionable_events),
    }


def enrich_universe_change_rates(
    stocks: list[dict[str, Any]],
    *,
    max_fetch: int = 100,
    quote_fetcher: Callable[[str], dict[str, Any] | None] | None = None,
) -> None:
    """Attach change_rate_pct to universe rows (in-place, top liquidity first)."""
    def _fetch(t: str) -> dict[str, Any] | None:
        if quote_fetcher:
            return quote_fetcher(t)
        try:
            from data.kis_client import get_price

            return get_price(t)
        except Exception:
            return None

    ordered = sorted(
        stocks,
        key=lambda r: _f(r, "avg_trading_value_20d_krw"),
        reverse=True,
    )[:max_fetch]
    for row in ordered:
        if _change_rate(row) != 0:
            continue
        ticker = str(row.get("ticker", "")).zfill(6)
        quote = _fetch(ticker)
        if quote:
            row["change_rate_pct"] = float(quote.get("change_rate") or 0)
