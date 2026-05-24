"""Build sealed point-in-time snapshot for replay (KIS OHLCV primary, pykrx bulk fallback)."""

from __future__ import annotations

import uuid
from typing import Any

from src.trading.competition.ops.historical_seed import enrich_universe_historical, scout_teams_historical
from src.trading.competition.replay.evidence import (
    EvidenceRecord,
    make_flow_evidence,
    make_news_unverified_placeholder,
    make_price_evidence,
)
from src.trading.competition.universe.builder import load_eligible_universe


def decision_at_iso(trading_date: str) -> str:
    return f"{trading_date[:4]}-{trading_date[4:6]}-{trading_date[6:8]}T15:30:00+09:00"


def build_close_snapshot(
    trading_date: str,
    *,
    universe: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Sealed snapshot at market close for trading_date.
    All teams share the same snapshot_id.
    """
    stocks = list(universe if universe is not None else load_eligible_universe())
    enrich = enrich_universe_historical(stocks, trading_date)
    if not enrich.get("ok"):
        return {"ok": False, "error": enrich.get("error"), "enrich": enrich}

    decision_at = decision_at_iso(trading_date)
    snapshot_id = f"replay_{trading_date}_close_{uuid.uuid4().hex[:6]}"

    scouts, scout_meta = scout_teams_historical(stocks, trading_date)
    universe_by = {str(r["ticker"]).zfill(6): r for r in stocks}

    evidence_records: list[EvidenceRecord] = []
    for tid, candidates in scouts.items():
        for c in candidates:
            ticker = c.ticker
            row = universe_by.get(ticker, {})
            evidence_records.append(
                make_price_evidence(
                    evidence_id=f"price:{ticker}:{trading_date}",
                    ticker=ticker,
                    decision_at=decision_at,
                    trading_date=trading_date,
                    close_krw=int(row.get("current_price_krw") or 0),
                    change_rate_pct=row.get("change_rate_pct"),
                )
            )
            if tid == "C" and c.metrics.get("foreign_net") is not None:
                evidence_records.append(
                    make_flow_evidence(
                        evidence_id=f"flow:{ticker}:{trading_date}",
                        ticker=ticker,
                        decision_at=decision_at,
                        trading_date=trading_date,
                        foreign_net=c.metrics.get("foreign_net"),
                    )
                )

    evidence_records.append(
        make_news_unverified_placeholder(
            evidence_id=f"news:unverified:{trading_date}",
            decision_at=decision_at,
            reason="historical_news_timestamp_not_verified",
        )
    )

    return {
        "ok": True,
        "snapshot_id": snapshot_id,
        "decision_at": decision_at,
        "trading_date": trading_date,
        "universe_count": len(stocks),
        "eligible_universe": stocks,
        "universe_by_ticker": universe_by,
        "team_scouts": {tid: [c.to_dict() for c in scouts[tid]] for tid in scouts},
        "scout_meta": scout_meta,
        "evidence_records": [e.to_dict() for e in evidence_records],
        "enrich": enrich,
        "constraints": {
            "no_web_search": True,
            "no_live_api_enrich": True,
            "news_verified_for_team_b": False,
        },
    }
