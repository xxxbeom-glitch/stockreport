"""Event scan orchestration."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any, Callable

from src.trading.competition.constants import TEAM_IDS
from src.trading.competition.events.analyzer import analyze_signals
from src.trading.competition.events.deduplicator import filter_new_signals
from src.trading.competition.events.detector import scan_ticker
from src.trading.competition.events.gate import apply_actionable_gate
from src.trading.competition.events.models import ActionableEvent, RawSignal
from src.trading.competition.events.store import (
    append_actionable_event,
    append_gate_rejected,
    append_raw_signal,
    save_scan_summary,
)
from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.positions import load_all_positions
from src.trading.competition.universe.builder import load_eligible_universe

logger = logging.getLogger(__name__)


def build_position_watch_map() -> dict[str, dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"name": "", "holding_teams": []}
    )
    all_pos = load_all_positions()
    for team_id in TEAM_IDS:
        tp = all_pos.get(team_id)
        if not tp:
            continue
        for pos in tp.positions:
            if pos.quantity <= 0:
                continue
            code = str(pos.ticker).zfill(6)
            entry = by_ticker[code]
            entry["name"] = pos.name or entry["name"] or code
            if team_id not in entry["holding_teams"]:
                entry["holding_teams"].append(team_id)
    return dict(by_ticker)


def build_eligible_map() -> dict[str, dict[str, Any]]:
    stocks = load_eligible_universe()
    return {
        str(s["ticker"]).zfill(6): s
        for s in stocks
        if s.get("ticker")
    }


def run_event_scan(
    *,
    scan_eligible: bool = True,
    scan_positions: bool = True,
    max_eligible_tickers: int = 0,
    include_dart: bool = True,
    include_news: bool = True,
    include_market: bool = True,
    use_gemini_analyzer: bool = False,
    ticker_scanner: Callable[..., list[RawSignal]] | None = None,
) -> dict[str, Any]:
    """
    Full event scan pipeline.

    Flow:
      detect → raw_signals (all)
      → dedup
      → actionable gate (validation + scoring + caps)
      → optional analyzer AI (gate-passed only)
      → actionable_events
    """
    scanner = ticker_scanner or scan_ticker
    all_signals: list[RawSignal] = []
    position_map = build_position_watch_map() if scan_positions else {}
    eligible_map = build_eligible_map() if scan_eligible else {}

    for ticker, info in position_map.items():
        name = info.get("name") or ticker
        teams = list(info.get("holding_teams") or [])
        all_signals.extend(
            scanner(
                ticker,
                name,
                scope="position_holding",
                holding_teams=teams,
                include_dart=include_dart,
                include_news=include_news,
                include_market=include_market,
                stock_meta=info,
            )
        )

    eligible_tickers = list(eligible_map.keys())
    if max_eligible_tickers > 0:
        eligible_tickers = eligible_tickers[:max_eligible_tickers]

    for ticker in eligible_tickers:
        meta = eligible_map[ticker]
        name = str(meta.get("name") or ticker)
        teams = position_map.get(ticker, {}).get("holding_teams", [])
        all_signals.extend(
            scanner(
                ticker,
                name,
                scope="eligible_candidate",
                holding_teams=teams,
                include_dart=include_dart,
                include_news=include_news,
                include_market=include_market,
                stock_meta=meta,
            )
        )

    new_signals, dup_signals = filter_new_signals(all_signals)

    for sig in new_signals:
        append_raw_signal(sig.to_dict())

    gate_result = apply_actionable_gate(new_signals)
    for rej in gate_result.rejected:
        append_gate_rejected(rej.to_dict())

    gate_passed_signals = [p.signal for p in gate_result.passed]
    analyzed = analyze_signals(gate_passed_signals, use_gemini=use_gemini_analyzer)

    passed_by_signal_id = {p.signal.signal_id: p for p in gate_result.passed}
    actionable_events: list[ActionableEvent] = []
    for evt in analyzed:
        # match by event_id prefix evt_{signal_id}
        sid = evt.event_id.replace("evt_", "", 1)
        gp = passed_by_signal_id.get(sid)
        if gp is None:
            for p in gate_result.passed:
                if evt.direct_tickers == [p.signal.ticker]:
                    gp = p
                    sid = p.signal.signal_id
                    break
        gate_score = gp.score.total if gp else 0
        actionable = ActionableEvent.from_analyzed(
            evt,
            signal_id=sid,
            gate_score=gate_score,
            gate_auto_pass=gp.score.auto_pass if gp else False,
            market_reaction_confirmed=gp.score.market_reaction_confirmed if gp else False,
            gate_reasons=gp.score.reasons if gp else [],
        )
        actionable_events.append(actionable)
        append_actionable_event(actionable.to_dict())

    type_counts_raw = Counter(s.event_type for s in new_signals)
    type_counts_actionable = Counter(e.event_type for e in actionable_events)
    scope_counts = Counter(s.scope for s in new_signals)
    gate_reject_stages = gate_result.summary_counts()

    summary = {
        "generated_at": now_kst_iso(),
        "eligible_tickers_scanned": len(eligible_tickers),
        "position_tickers_scanned": len(position_map),
        "signals_total": len(all_signals),
        "signals_new": len(new_signals),
        "signals_duplicate": len(dup_signals),
        "gate_passed": len(gate_result.passed),
        "gate_rejected": len(gate_result.rejected),
        "gate_reject_by_stage": gate_reject_stages,
        "actionable_events": len(actionable_events),
        "events_requiring_position_review": sum(
            1 for e in actionable_events if e.requires_position_review
        ),
        "by_event_type_raw": dict(type_counts_raw),
        "by_event_type_actionable": dict(type_counts_actionable),
        "by_scope": dict(scope_counts),
        "position_watch_tickers": list(position_map.keys()),
        "reduction_ratio": (
            round(len(actionable_events) / len(new_signals), 3)
            if new_signals
            else 0.0
        ),
        "data_sources": {
            "eligible_universe": scan_eligible,
            "positions": scan_positions,
            "dart": include_dart,
            "news": include_news,
            "market": include_market,
            "gemini_analyzer": use_gemini_analyzer,
            "actionable_gate": True,
        },
    }
    save_scan_summary(summary)

    return {
        "ok": True,
        "summary": summary,
        "new_signals": [s.to_dict() for s in new_signals],
        "actionable_events": [e.to_dict() for e in actionable_events],
        "gate_rejected_count": len(gate_result.rejected),
    }
