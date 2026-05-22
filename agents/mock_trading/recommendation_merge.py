# -*- coding: utf-8 -*-
"""에이전트별 추천 → 웹 표시용 ticker 병합."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from agents.mock_trading.models import AGENT_SPECS, CONSENSUS_LABELS


def merge_recommendations(
    agent_results: list[dict[str, Any]],
    grok_validation: list[dict[str, Any]],
    universe_by_ticker: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """merged_recommendations.json 본문."""
    by_ticker: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "recommending_agents": [],
            "agent_keys": [],
            "ranks": {},
        }
    )

    display_by_key = {s.agent_key: s.display_name for s in AGENT_SPECS}

    for agent in agent_results:
        akey = agent.get("agent_key") or ""
        dname = agent.get("display_name") or display_by_key.get(akey, akey)
        for rec in agent.get("recommendations") or []:
            ticker = str(rec.get("ticker", "")).zfill(6)
            if not ticker:
                continue
            slot = by_ticker[ticker]
            if dname not in slot["recommending_agents"]:
                slot["recommending_agents"].append(dname)
            if akey not in slot["agent_keys"]:
                slot["agent_keys"].append(akey)
            slot["ranks"][akey] = rec.get("rank")
            slot["latest_pick"] = rec

    grok_map = {str(g.get("ticker", "")).zfill(6): g for g in grok_validation}

    merged_cards: list[dict[str, Any]] = []
    for ticker, agg in sorted(by_ticker.items()):
        count = len(agg["recommending_agents"])
        consensus = CONSENSUS_LABELS.get(count, f"{count}개 모델 추천")
        uni = universe_by_ticker.get(ticker, {})
        pick = agg.get("latest_pick") or {}
        card = {
            "ticker": ticker,
            "name": pick.get("name") or uni.get("name"),
            "sector_group": pick.get("sector_group") or uni.get("sector_group"),
            "recommendation_count": count,
            "consensus_label": consensus,
            "recommending_agents": agg["recommending_agents"],
            "agent_keys": agg["agent_keys"],
            "entry_price": pick.get("entry_price"),
            "entry_range": pick.get("entry_range"),
            "target_price": pick.get("target_price"),
            "reasons_sample": (pick.get("reasons") or [])[:2],
            "current_price": uni.get("current_price"),
            "grok_validation": grok_map.get(ticker),
        }
        merged_cards.append(card)

    merged_cards.sort(key=lambda c: (-c["recommendation_count"], c.get("name") or ""))

    return {
        "merged_cards": merged_cards,
        "ticker_count": len(merged_cards),
    }
