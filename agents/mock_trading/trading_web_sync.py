# -*- coding: utf-8 -*-
"""merged/weekly 추천 JSON → kr_trading용 trading_data.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.models import SECTOR_LABELS
from agents.mock_trading.plain_language import build_plain_copy, enrich_merged_card

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "data" / "mock_trading"
MERGED_PATH = MOCK_DIR / "merged_recommendations.json"
WEEKLY_PATH = MOCK_DIR / "weekly_recommendations.json"
STATE_PATH = MOCK_DIR / "trading_state.json"
OUT_PATH = MOCK_DIR / "trading_data.json"

ALLOWED_STATUSES = frozenset({"진행 중", "익절"})


def normalize_display_status(value: str | None) -> str:
    """가상투자 UI 허용 상태만 표시."""
    s = str(value or "").strip()
    if s in ("익절", "익절 완료"):
        return "익절"
    if s in ("진행 중", "투자 진행 중"):
        return "진행 중"
    return "—"


def _status_for_ticker(
    ticker: str,
    *,
    week_doc: dict[str, Any] | None,
    saved_states: dict[str, str],
) -> str:
    if week_doc:
        for row in week_doc.get("virtualTakeProfits") or []:
            if str(row.get("ticker", "")).zfill(6) == ticker:
                return "익절"
        for row in week_doc.get("virtualBuys") or []:
            if str(row.get("ticker", "")).zfill(6) == ticker:
                return "진행 중"
    return normalize_display_status(saved_states.get(ticker))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _aggregate_picks_by_ticker(weekly: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """ticker → reasons, risk_factors, agent picks."""
    by_ticker: dict[str, dict[str, Any]] = {}
    for agent in weekly.get("agents") or []:
        akey = agent.get("agent_key") or ""
        dname = agent.get("display_name") or akey
        for rec in agent.get("recommendations") or []:
            ticker = str(rec.get("ticker", "")).zfill(6)
            if not ticker:
                continue
            slot = by_ticker.setdefault(
                ticker,
                {
                    "reasons": [],
                    "risk_factors": [],
                    "picks_by_agent": [],
                },
            )
            for r in rec.get("reasons") or []:
                if r and r not in slot["reasons"]:
                    slot["reasons"].append(r)
            for rf in rec.get("risk_factors") or []:
                if rf and rf not in slot["risk_factors"]:
                    slot["risk_factors"].append(rf)
            slot["picks_by_agent"].append(
                {
                    "agent_key": akey,
                    "display_name": dname,
                    "rank": rec.get("rank"),
                }
            )
    return by_ticker


def _grok_warnings(card: dict[str, Any]) -> list[str]:
    grok = card.get("grok_validation") or {}
    return list(grok.get("warning_signals") or [])


def _format_agents(card: dict[str, Any]) -> str:
    agents = card.get("recommending_agents") or []
    return ", ".join(agents) if agents else "—"


def _format_reasons(reasons: list[str], sample: list[str]) -> str:
    merged: list[str] = []
    for r in list(reasons) + list(sample):
        if r and r not in merged:
            merged.append(r)
    return "\n".join(merged[:4]) if merged else "—"


def _format_risks(risk_factors: list[str], grok_warnings: list[str]) -> str:
    parts: list[str] = []
    for r in risk_factors:
        if r and r not in parts:
            parts.append(r)
    for w in grok_warnings:
        if w and w not in parts:
            parts.append(w)
    return "\n".join(parts[:4]) if parts else "—"


def build_trading_payload(
    merged: dict[str, Any],
    weekly: dict[str, Any],
    *,
    state_path: Path = STATE_PATH,
    data_source: str = "merged_recommendations.json",
    week_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    picks = _aggregate_picks_by_ticker(weekly)

    saved_states: dict[str, str] = {}
    if state_path.is_file():
        state_doc = _load_json(state_path)
        for row in state_doc.get("holdings") or []:
            t = str(row.get("ticker", "")).zfill(6)
            if t and row.get("status"):
                saved_states[t] = str(row["status"])

    week_id = merged.get("week_id") or weekly.get("week_id") or ""
    generated_at = merged.get("generated_at") or weekly.get("generated_at") or ""
    cards = merged.get("merged_cards") or []

    holdings: list[dict[str, Any]] = []
    for card in cards:
        ticker = str(card.get("ticker", "")).zfill(6)
        pick = picks.get(ticker, {})
        card_plain = (
            card
            if card.get("plainReason")
            else enrich_merged_card(
                card,
                extra_reasons=pick.get("reasons") or [],
                extra_risks=pick.get("risk_factors") or [],
            )
        )
        sector_key = card_plain.get("sector_group") or ""
        sector_label = SECTOR_LABELS.get(str(sector_key), str(sector_key))
        grok_warn = _grok_warnings(card_plain)
        reasons = pick.get("reasons") or []
        risks = pick.get("risk_factors") or []
        plain = (
            {
                "plainReason": card_plain.get("plainReason"),
                "plainRisk": card_plain.get("plainRisk"),
                "viewGuide": card_plain.get("viewGuide"),
            }
            if card_plain.get("plainReason")
            else build_plain_copy(
                name=str(card_plain.get("name") or ""),
                reason_lines=list(card_plain.get("reasons_sample") or []) + reasons,
                risk_lines=risks,
                grok_validation=card_plain.get("grok_validation"),
            )
        )

        entry = int(card_plain.get("entry_price") or card_plain.get("current_price") or 0)
        current = card_plain.get("current_price")
        try:
            current_int = int(round(float(current))) if current is not None else entry
        except (TypeError, ValueError):
            current_int = entry

        holdings.append(
            {
                "ticker": ticker,
                "name": card_plain.get("name") or "",
                "sector": sector_label,
                "sector_group": sector_key,
                "business_summary": sector_label,
                "buy_amount": entry,
                "buy_price": entry,
                "current_price": current_int,
                "eval_amount": current_int,
                "price_status": "ok",
                "return_pct": 0.0 if entry > 0 else None,
                "agent": _format_agents(card_plain),
                "recommending_agents": list(card_plain.get("recommending_agents") or []),
                "agent_keys": list(card_plain.get("agent_keys") or []),
                "recommendation_count": int(card_plain.get("recommendation_count") or 0),
                "consensus_label": card_plain.get("consensus_label") or "",
                "selection_reason": _format_reasons(
                    reasons, list(card_plain.get("reasons_sample") or [])
                ),
                "risk_factors_text": _format_risks(risks, grok_warn),
                "risk_factors": risks,
                "plain_reason": plain["plainReason"],
                "plain_risk": plain["plainRisk"],
                "view_guide": plain["viewGuide"],
                "grok_warnings": grok_warn,
                "entry_range": card_plain.get("entry_range"),
                "target_price": card_plain.get("target_price"),
                "status": _status_for_ticker(
                    ticker, week_doc=week_doc, saved_states=saved_states
                ),
                "grok_validation": card_plain.get("grok_validation"),
            }
        )

    agents_panel: list[dict[str, Any]] = []
    for agent in weekly.get("agents") or []:
        names = [
            str(r.get("name") or "")
            for r in (agent.get("recommendations") or [])
            if r.get("name")
        ]
        agents_panel.append(
            {
                "agent_key": agent.get("agent_key"),
                "name": agent.get("display_name") or agent.get("agent_key"),
                "model_id": agent.get("model_id") or "",
                "perspective": agent.get("perspective") or "",
                "cumulative_return_pct": 0.0,
                "pick_names": names,
            }
        )

    now = datetime.now(KST)
    as_of = generated_at[:10] if len(generated_at) >= 10 else now.strftime("%Y-%m-%d")

    payload: dict[str, Any] = {
        "pageMeta": {
            "title": "모의 투자 시스템",
            "market": "한국시장",
            "week_id": week_id,
            "as_of_date": as_of,
            "weekday_label": f"{as_of} 주간 추천",
            "updated_at": now.strftime("%H:%M 업데이트"),
            "data_source": data_source,
            "recommendation_count": len(holdings),
        },
        "recommendations": {
            "week_id": week_id,
            "ticker_count": len(holdings),
            "source_candidate_count": int(
                (weekly.get("universe_summary") or {}).get("ai_input_candidate_count") or 0
            ),
        },
        "holdings": holdings,
        "rankings": [],
        "agents": agents_panel,
        "excluded_candidates": [],
    }
    return payload


def build_trading_data(
    *,
    merged_path: Path = MERGED_PATH,
    weekly_path: Path = WEEKLY_PATH,
    state_path: Path = STATE_PATH,
    out_path: Path = OUT_PATH,
) -> dict[str, Any]:
    merged = _load_json(merged_path)
    weekly = _load_json(weekly_path) if weekly_path.is_file() else {}
    payload = build_trading_payload(
        merged,
        weekly,
        state_path=state_path,
        data_source="merged_recommendations.json",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def build_trading_data_from_firestore_doc(
    firestore_doc: dict[str, Any],
    *,
    state_path: Path = STATE_PATH,
) -> dict[str, Any]:
    from agents.mock_trading.weekly_recommendations_store import firestore_doc_to_local

    merged, weekly = firestore_doc_to_local(firestore_doc)
    source = firestore_doc.get("persist_backend") or "firestore"
    path = firestore_doc.get("firestore_path") or "weeklyRecommendations"
    return build_trading_payload(
        merged,
        weekly,
        state_path=state_path,
        data_source=f"{source}:{path}",
        week_doc=firestore_doc,
    )
