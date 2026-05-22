# -*- coding: utf-8 -*-
"""AI 에이전트 판단 — 통과 종목만 가상매수 후보 (week_id 미사용)."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.compact_input import load_compact_universe
from agents.mock_trading.kis_market_watch import fetch_quote, quote_to_int_price
from agents.mock_trading.models import AGENT_SPECS
from agents.mock_trading.recommendation_agents import (
    check_provider_ready,
    run_all_recommendation_agents,
)
from agents.mock_trading.recommendation_validate import validate_agent_recommendations

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
COMPACT_PATH = ROOT / "data" / "mock_trading" / "ai_candidate_context_compact.json"

PASS_CONFIDENCE = frozenset({"high", "medium"})


def _load_candidates(*, compact_path: Path = COMPACT_PATH) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, meta, err = load_compact_universe(compact_path)
    if err:
        return [], {"error": err}
    return rows, meta


def _agent_passes(rec: dict[str, Any]) -> bool:
    conf = str(rec.get("confidence") or "medium").lower()
    if conf not in PASS_CONFIDENCE:
        return False
    ticker = str(rec.get("ticker") or "").zfill(6)
    if not ticker or not rec.get("name"):
        return False
    try:
        entry = int(rec.get("entry_price") or 0)
        target = int(rec.get("target_price") or 0)
    except (TypeError, ValueError):
        return False
    if entry <= 0 or target <= entry:
        return False
    if not (rec.get("plain_reason") or rec.get("reasons")):
        return False
    return True


def run_agent_judgment(
    *,
    dry_run: bool = False,
    compact_path: Path = COMPACT_PATH,
) -> dict[str, Any]:
    """4개 에이전트 평가 → 통과 picks (ticker 단위 병합)."""
    candidates, compact_meta = _load_candidates(compact_path=compact_path)
    if not candidates:
        return {
            "ok": False,
            "error": "no_candidates",
            "agents": [],
            "passed_picks": [],
        }

    if dry_run:
        stubs = []
        for spec in AGENT_SPECS:
            stubs.append(
                {
                    "agent_key": spec.agent_key,
                    "display_name": spec.display_name,
                    "recommendations": [],
                    "skipped": True,
                    "skip_reason": "dry_run",
                }
            )
        return {"ok": True, "dry_run": True, "agents": stubs, "passed_picks": []}

    agent_results, agent_errors = run_all_recommendation_agents(candidates)
    passed_by_ticker: dict[str, dict[str, Any]] = {}

    allowed = {str(c.get("ticker", "")).zfill(6) for c in candidates if c.get("ticker")}
    name_by = {str(c.get("ticker", "")).zfill(6): str(c.get("name") or "") for c in candidates}

    for agent in agent_results:
        akey = agent.get("agent_key") or ""
        dname = agent.get("display_name") or akey
        recs = agent.get("recommendations") or []
        valid, _ = validate_agent_recommendations(
            recs,
            allowed_tickers=allowed,
            name_by_ticker=name_by,
        )
        for rec in valid:
            if not _agent_passes(rec):
                continue
            ticker = str(rec.get("ticker")).zfill(6)
            entry_px = int(rec.get("entry_price") or 0)
            slot = passed_by_ticker.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "name": rec.get("name"),
                    "sector_group": rec.get("sector_group"),
                    "plain_reason": rec.get("plain_reason"),
                    "agent_keys": [],
                    "agent_names": [],
                    "reasons": [],
                    "trigger_reason": [],
                    "limit_prices": [],
                },
            )
            if entry_px > 0 and entry_px not in slot["limit_prices"]:
                slot["limit_prices"].append(entry_px)
            if akey and akey not in slot["agent_keys"]:
                slot["agent_keys"].append(akey)
            if dname and dname not in slot["agent_names"]:
                slot["agent_names"].append(dname)
            for r in rec.get("reasons") or []:
                if r and r not in slot["reasons"]:
                    slot["reasons"].append(r)
            label = f"{dname} 추천"
            if label not in slot["trigger_reason"]:
                slot["trigger_reason"].append(label)

    picks = list(passed_by_ticker.values())
    for pick in picks:
        prices = [int(p) for p in pick.pop("limit_prices", []) if int(p) > 0]
        pick["limit_price"] = min(prices) if prices else 0
        quote = fetch_quote(pick["ticker"])
        pick["signal_price"] = quote_to_int_price(quote)
        pick["signal_at"] = datetime.now(KST).isoformat(timespec="seconds")

    return {
        "ok": True,
        "agents": agent_results,
        "agent_errors": agent_errors,
        "passed_picks": picks,
        "candidate_count": len(candidates),
        "provider_audit": [
            {
                "agent_key": s.agent_key,
                "ready": check_provider_ready(s.provider)[0],
            }
            for s in AGENT_SPECS
        ],
    }
