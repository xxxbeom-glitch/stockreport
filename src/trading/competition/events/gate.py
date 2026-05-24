"""Actionable event gate — filters raw signals before AI team calls."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from src.trading.competition.events.models import RawSignal
from src.trading.competition.events.scoring import (
    MAX_ACTIONABLE_NEWS_PER_TICKER_ELIGIBLE,
    MAX_ACTIONABLE_PER_TICKER_ELIGIBLE,
    MAX_ACTIONABLE_PER_TICKER_POSITION,
    GateScore,
    score_signal,
)
from src.trading.competition.events.validator import validate_signal

logger = logging.getLogger(__name__)


@dataclass
class GateRejected:
    signal: RawSignal
    stage: str
    reason: str
    score: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "reason": self.reason,
            "score": self.score,
            "signal": self.signal.to_dict(),
        }


@dataclass
class GatePassed:
    signal: RawSignal
    score: GateScore

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal.to_dict(),
            "gate_score": self.score.total,
            "gate_auto_pass": self.score.auto_pass,
            "market_reaction_confirmed": self.score.market_reaction_confirmed,
            "gate_reasons": self.score.reasons,
        }


@dataclass
class GateResult:
    passed: list[GatePassed] = field(default_factory=list)
    rejected: list[GateRejected] = field(default_factory=list)

    def summary_counts(self) -> dict[str, int]:
        from collections import Counter

        return dict(Counter(r.stage for r in self.rejected))


def enrich_ticker_market_metrics(
    signals: list[RawSignal],
    *,
    quote_fetcher: Callable[[str], dict[str, Any] | None] | None = None,
) -> None:
    """Fill change_rate / tv_ratio on signals missing metrics (one KIS call per ticker)."""
    by_ticker: dict[str, list[RawSignal]] = defaultdict(list)
    for sig in signals:
        if sig.metrics.get("change_rate_pct") is not None:
            continue
        by_ticker[sig.ticker].append(sig)

    if not by_ticker:
        return

    def _fetch(ticker: str) -> dict[str, Any] | None:
        if quote_fetcher:
            return quote_fetcher(ticker)
        try:
            from data.kis_client import get_price

            return get_price(ticker.zfill(6))
        except Exception:
            return None

    for ticker, sigs in by_ticker.items():
        quote = _fetch(ticker)
        if not quote:
            continue
        change = float(quote.get("change_rate") or 0)
        for sig in sigs:
            sig.metrics.setdefault("change_rate_pct", change)


def apply_per_ticker_caps(passed: list[GatePassed]) -> tuple[list[GatePassed], list[GateRejected]]:
    """
    Limit actionable events per ticker to control AI call volume.
    Position protection events bypass news caps but still respect position max.
    """
    eligible_counts: dict[str, int] = defaultdict(int)
    eligible_news: dict[str, int] = defaultdict(int)
    position_counts: dict[str, int] = defaultdict(int)

    kept: list[GatePassed] = []
    capped: list[GateRejected] = []

    # Sort by score desc so best signals survive caps
    ordered = sorted(passed, key=lambda p: p.score.total, reverse=True)

    for item in ordered:
        ticker = item.signal.ticker
        scope = item.signal.scope
        etype = item.signal.event_type

        if scope == "position_holding":
            if item.score.auto_pass or etype in ("POSITION_RISK_ALERT", "TRADING_STATUS_CHANGE"):
                kept.append(item)
                continue
            if position_counts[ticker] >= MAX_ACTIONABLE_PER_TICKER_POSITION:
                capped.append(
                    GateRejected(item.signal, "cap", "position_ticker_cap", item.score.total)
                )
                continue
            position_counts[ticker] += 1
            kept.append(item)
            continue

        # eligible_candidate
        if etype == "NEWS_MATERIAL":
            if eligible_news[ticker] >= MAX_ACTIONABLE_NEWS_PER_TICKER_ELIGIBLE:
                capped.append(
                    GateRejected(item.signal, "cap", "eligible_news_cap", item.score.total)
                )
                continue
            eligible_news[ticker] += 1

        if eligible_counts[ticker] >= MAX_ACTIONABLE_PER_TICKER_ELIGIBLE:
            capped.append(
                GateRejected(item.signal, "cap", "eligible_ticker_cap", item.score.total)
            )
            continue

        eligible_counts[ticker] += 1
        kept.append(item)

    return kept, capped


def apply_actionable_gate(
    signals: list[RawSignal],
    *,
    enrich_market: bool = True,
    quote_fetcher: Callable[[str], dict[str, Any] | None] | None = None,
) -> GateResult:
    """
    raw_signals → validation → scoring → caps.

    Does NOT run analyzer; returns signals cleared for optional AI + team routing.
    """
    result = GateResult()

    if enrich_market:
        enrich_ticker_market_metrics(signals, quote_fetcher=quote_fetcher)

    scored: list[GatePassed] = []
    for sig in signals:
        ok, reason = validate_signal(sig)
        if not ok:
            result.rejected.append(GateRejected(sig, "validation", reason))
            continue

        gs = score_signal(sig)
        if not gs.passes_threshold:
            result.rejected.append(
                GateRejected(sig, "scoring", "below_threshold", gs.total)
            )
            continue
        scored.append(GatePassed(sig, gs))

    kept, capped = apply_per_ticker_caps(scored)
    result.passed.extend(kept)
    result.rejected.extend(capped)

    return result
