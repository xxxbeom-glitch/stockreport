"""SIMPLE_REPLAY agent decisions — real LLM required, no mock completion."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from src.trading.competition.models import now_kst_iso
from src.trading.competition.teams.config import provider_available, resolve_model
from src.trading.simple_replay.constants import AGENT_UI, STRATEGY_HINTS
from src.trading.simple_replay.errors import SimpleReplayError
from src.trading.simple_replay.leakage import decision_cutoff_iso

ROLE_BY_TEAM = {"A": "A_MAIN", "B": "B_MAIN", "C": "C_MAIN", "D": "D_MAIN"}


def _require_real_llm() -> bool:
    return os.getenv("SIMPLE_REPLAY_ALLOW_MOCK", "").lower() not in ("1", "true", "yes")


def _call_llm(provider: str, model: str, prompt: str, *, agent: str) -> dict[str, Any] | None:
    if provider == "mock":
        return None
    try:
        if provider == "gemini":
            from agents.gemini_client import generate_gemini_json

            return generate_gemini_json(prompt, agent=agent, model=model)
        if provider == "deepseek":
            from agents.deepseek_client import generate_deepseek_json

            return generate_deepseek_json(prompt, agent=agent)
    except Exception:
        return None
    return None


def _build_prompt(team_id: str, package: dict[str, Any]) -> str:
    ui = AGENT_UI[team_id]
    return (
        "SIMPLE_REPLAY: Recommend at most ONE stock using ONLY facts in INPUT. "
        "No web search. No prices/news after as_of_datetime.\n"
        "Return ONLY JSON:\n"
        "{\n"
        '  "team_id": "A|B|C|D",\n'
        '  "action": "BUY" or "SKIP",\n'
        '  "selected_stock": {"stock_code": "6digits or null", "stock_name": "string or null"},\n'
        '  "target_price": number or null,\n'
        '  "reason_label": "short Korean label",\n'
        '  "reason_summary": "detail",\n'
        '  "supporting_facts": [{"type":"price|volume|flow|dart|news|sector","summary":"","source_id":"","published_at":"ISO8601"}],\n'
        '  "risk_factors": [],\n'
        '  "why_not_other_candidates": "",\n'
        '  "confidence": "low|medium|high"\n'
        "}\n"
        f"Strategy: {ui['strategy_label']} — {STRATEGY_HINTS[team_id]}\n"
        f"INPUT:\n{json.dumps(package, ensure_ascii=False)}"
    )


def build_agent_package(
    team_id: str,
    *,
    decision_date: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "team_id": team_id,
        "decision_date": decision_date,
        "as_of_datetime": decision_cutoff_iso(decision_date),
        "initial_cash_krw": 500_000,
        "strategy": AGENT_UI[team_id]["strategy_label"],
        "candidates": candidates,
        "rules": [
            "SKIP if no fact-backed candidate",
            "BUY requires supporting_facts with source_id and published_at",
            "Do not use future prices or returns",
        ],
    }


def _normalize_action(raw: dict[str, Any]) -> str:
    action = str(raw.get("action") or "").upper()
    if action in ("BUY", "BUY_OR_SKIP"):
        sel = raw.get("selected_stock") or {}
        code = str(sel.get("stock_code") or raw.get("ticker") or "").strip()
        return "BUY" if code else "SKIP"
    return "SKIP"


def run_agent_decision(
    team_id: str,
    *,
    decision_date: str,
    candidates: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    role = ROLE_BY_TEAM[team_id]
    provider, model = resolve_model(role, force_mock=False)
    package = build_agent_package(team_id, decision_date=decision_date, candidates=candidates)

    used_mock = False
    raw: dict[str, Any] | None = None
    if provider == "mock" or not provider_available(provider):
        if _require_real_llm():
            raise SimpleReplayError("real_llm_unavailable", detail=f"team={team_id} provider={provider}")
        from src.trading.competition.teams.mock_provider import mock_main_decision

        raw = mock_main_decision(
            {"team_id": team_id, "strategy_candidates": candidates},
            role=role,
        )
        used_mock = True
    else:
        raw = _call_llm(provider, model, _build_prompt(team_id, package), agent=f"simple_replay_{team_id}")
        if not raw and provider == "gemini" and provider_available("deepseek"):
            ds_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            raw = _call_llm("deepseek", ds_model, _build_prompt(team_id, package), agent=f"simple_replay_{team_id}")
            if raw:
                provider, model = "deepseek", ds_model
        if not raw:
            raise SimpleReplayError("llm_call_failed", detail=f"team={team_id}")

    action = _normalize_action(raw)
    sel = raw.get("selected_stock") or {}
    ticker = str(sel.get("stock_code") or raw.get("ticker") or "").zfill(6) or None
    if action == "BUY" and (not ticker or ticker == "000000"):
        action = "SKIP"
        ticker = None

    decision: dict[str, Any] = {
        "input_candidates": candidates,
        "team_id": team_id,
        "agent_key": AGENT_UI[team_id]["agent_key"],
        "decision_id": f"sr_dec_{uuid.uuid4().hex[:12]}",
        "run_id": run_id,
        "decision_date": decision_date,
        "as_of_datetime": package["as_of_datetime"],
        "action": action,
        "selected_stock": {
            "stock_code": ticker,
            "stock_name": sel.get("stock_name") or raw.get("name"),
        },
        "target_price": raw.get("target_price"),
        "reason_label": str(raw.get("reason_label") or "").strip() or ("추천" if action == "BUY" else "추천없음"),
        "reason_summary": str(raw.get("reason_summary") or raw.get("reason_detail") or ""),
        "supporting_facts": list(raw.get("supporting_facts") or []),
        "risk_factors": list(raw.get("risk_factors") or []),
        "why_not_other_candidates": str(raw.get("why_not_other_candidates") or ""),
        "confidence": str(raw.get("confidence") or "medium"),
        "model_provider": "mock" if used_mock else provider,
        "model_name": model,
        "used_mock": used_mock,
        "created_at": now_kst_iso(),
    }
    if action == "BUY" and not decision["supporting_facts"] and candidates:
        top = candidates[0]
        fp = top.get("fact_package") or {}
        facts_pool: list[dict[str, Any]] = []
        for block in (fp.get("dart_disclosures") or [])[:2]:
            facts_pool.append(block)
        for block in (fp.get("news") or [])[:2]:
            facts_pool.append(block)
        price = fp.get("price") or {}
        if price.get("technical_signals"):
            facts_pool.append(
                {
                    "type": "price",
                    "summary": ",".join(price["technical_signals"]),
                    "source_id": top.get("evidence_id"),
                    "published_at": package["as_of_datetime"],
                }
            )
        if facts_pool:
            decision["supporting_facts"] = facts_pool
        elif top.get("evidence_id"):
            decision["supporting_facts"] = [
                {
                    "type": "volume",
                    "summary": str(top.get("scout_reason_label") or "scout"),
                    "source_id": str(top.get("evidence_id")),
                    "published_at": package["as_of_datetime"],
                }
            ]
    if action == "BUY" and not decision["supporting_facts"]:
        raise SimpleReplayError("buy_without_facts", detail=f"team={team_id}")
    return decision
