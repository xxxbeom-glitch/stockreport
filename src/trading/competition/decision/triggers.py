"""Build Phase 4 decision triggers (3 types)."""

from __future__ import annotations

import uuid
from typing import Any

from src.trading.competition.constants import TEAM_IDS
from src.trading.competition.decision.models import DecisionTrigger
from src.trading.competition.decision.strategy_scouts import scout_all_teams
from src.trading.competition.events.store import load_actionable_events
from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.accounts import load_all_accounts
from src.trading.competition.storage.positions import load_all_positions
from src.trading.competition.universe.builder import load_eligible_universe


def _trigger_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _position_payload(team_id: str) -> list[dict[str, Any]]:
    tp = load_all_positions().get(team_id)
    if not tp:
        return []
    out: list[dict[str, Any]] = []
    for pos in tp.positions:
        if pos.quantity <= 0:
            continue
        out.append(
            {
                "ticker": pos.ticker,
                "name": pos.name,
                "quantity": pos.quantity,
                "avg_price_krw": pos.avg_price_krw,
                "current_price_krw": pos.current_price_krw,
                "eval_return_pct": pos.eval_return_pct,
                "eval_pnl_krw": pos.eval_pnl_krw,
                "buy_reason_label": pos.buy_reason_label,
                "target_price_krw": pos.target_price_krw,
                "risk_status": pos.risk_status,
            }
        )
    return out


def build_strategy_triggers(
    session_id: str,
    *,
    scouts: dict[str, list] | None = None,
    enrich_market: bool = True,
) -> list[DecisionTrigger]:
    """
    STRATEGY_CANDIDATE_REVIEW — one per team per session.

    Does not require actionable events. Teams scout eligible universe independently.
    """
    from src.trading.competition.decision.strategy_scouts import enrich_universe_change_rates

    universe = load_eligible_universe()
    if enrich_market and universe:
        enrich_universe_change_rates(universe, max_fetch=min(120, len(universe)))

    actionable = load_actionable_events()
    material: set[str] = set()
    for evt in actionable:
        et = evt.get("event_type", "")
        if et.startswith("DISCLOSURE") or et == "NEWS_MATERIAL":
            material.update(evt.get("direct_tickers") or [])

    team_candidates = scouts or scout_all_teams(
        universe=universe,
        material_tickers=material,
        actionable_events=actionable,
    )

    triggers: list[DecisionTrigger] = []
    for team_id in TEAM_IDS:
        cands = team_candidates.get(team_id) or []
        if not cands and team_id in ("A", "C", "D"):
            # Still emit trigger with empty candidates — team may HOLD/WAIT
            pass
        triggers.append(
            DecisionTrigger(
                trigger_id=_trigger_id("str"),
                trigger_type="STRATEGY_CANDIDATE_REVIEW",
                team_id=team_id,
                session_id=session_id,
                summary=f"팀 {team_id} 전략 후보 {len(cands)}건",
                priority="normal",
                candidates=[c.to_dict() for c in cands],
                context={"scout_mode": "eligible_universe", "candidate_count": len(cands)},
            )
        )
    return triggers


def build_actionable_event_triggers(
    session_id: str,
    *,
    events: list[dict[str, Any]] | None = None,
) -> list[DecisionTrigger]:
    """ACTIONABLE_EVENT_REVIEW — one trigger per (team, event) from actionable_events.jsonl."""
    rows = events if events is not None else load_actionable_events()
    triggers: list[DecisionTrigger] = []
    for evt in rows:
        event_id = str(evt.get("event_id") or "")
        if not event_id:
            continue
        evidence = list(evt.get("evidence_ids") or [])
        if not evidence:
            continue
        importance = str(evt.get("importance") or "MEDIUM")
        priority = "normal"
        if importance == "CRITICAL":
            priority = "critical"
        elif importance == "HIGH":
            priority = "high"

        for team_id in evt.get("affected_teams") or []:
            if team_id not in TEAM_IDS:
                continue
            triggers.append(
                DecisionTrigger(
                    trigger_id=_trigger_id("evt"),
                    trigger_type="ACTIONABLE_EVENT_REVIEW",
                    team_id=team_id,
                    session_id=session_id,
                    summary=str(evt.get("summary") or ""),
                    priority=priority,  # type: ignore[arg-type]
                    event_ids=[event_id],
                    evidence_ids=evidence,
                    candidates=[
                        {"ticker": t, "source": "actionable_event"}
                        for t in evt.get("direct_tickers") or []
                    ],
                    context={
                        "event_type": evt.get("event_type"),
                        "requires_position_review": evt.get("requires_position_review"),
                        "direction": evt.get("direction"),
                    },
                )
            )
    return triggers


def build_position_triggers(
    session_id: str,
    *,
    session_transition: bool = True,
    force_teams: set[str] | None = None,
) -> list[DecisionTrigger]:
    """
    POSITION_REVIEW — held positions re-evaluation.

    Fired on session transition for all teams with holdings, plus forced teams
    (e.g. from actionable risk events).
    """
    triggers: list[DecisionTrigger] = []
    accounts = load_all_accounts()

    for team_id in TEAM_IDS:
        positions = _position_payload(team_id)
        forced = force_teams and team_id in force_teams
        if not positions and not forced:
            continue
        if not session_transition and not forced:
            continue

        acc = accounts.get(team_id)
        cash = acc.cash_krw if acc else 0
        priority: str = "high" if forced else "normal"

        triggers.append(
            DecisionTrigger(
                trigger_id=_trigger_id("pos"),
                trigger_type="POSITION_REVIEW",
                team_id=team_id,
                session_id=session_id,
                summary=f"팀 {team_id} 보유 {len(positions)}종목 세션 재판단",
                priority=priority,  # type: ignore[arg-type]
                positions=positions,
                context={
                    "cash_krw": cash,
                    "session_transition": session_transition,
                    "forced_review": forced,
                },
            )
        )
    return triggers


def build_all_decision_triggers(
    session_id: str,
    *,
    include_strategy: bool = True,
    include_actionable: bool = True,
    include_position: bool = True,
    session_transition: bool = True,
    enrich_market: bool = True,
) -> list[DecisionTrigger]:
    """Assemble all Phase 4 trigger types for one session."""
    all_triggers: list[DecisionTrigger] = []

    if include_strategy:
        all_triggers.extend(
            build_strategy_triggers(session_id, enrich_market=enrich_market)
        )

    actionable_events = load_actionable_events() if include_actionable else []
    force_teams: set[str] = set()
    if include_actionable:
        evt_triggers = build_actionable_event_triggers(
            session_id, events=actionable_events
        )
        all_triggers.extend(evt_triggers)
        for evt in actionable_events:
            if evt.get("requires_position_review"):
                force_teams.update(evt.get("holding_teams") or [])
                force_teams.update(evt.get("affected_teams") or [])

    if include_position:
        all_triggers.extend(
            build_position_triggers(
                session_id,
                session_transition=session_transition,
                force_teams=force_teams or None,
            )
        )

    return all_triggers
