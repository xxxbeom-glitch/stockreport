# -*- coding: utf-8 -*-
"""merged/weekly 추천 JSON → kr_trading용 trading_data.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.models import SECTOR_LABELS
from agents.mock_trading.agent_catalog import normalize_agent_names
from agents.mock_trading.agent_performance_store import agent_panel_rows, recompute_and_persist
from agents.mock_trading.milestone_tracker import holding_fields_from_position
from agents.mock_trading.position_schema import position_to_ui_snake
from agents.mock_trading.plain_language import build_plain_copy, enrich_merged_card
from agents.mock_trading.virtual_positions_store import (
    import_from_week_doc,
    list_positions,
    positions_by_week,
    refresh_position_prices,
    sync_ledger_from_all_stored_weeks,
)

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "data" / "mock_trading"
MERGED_PATH = MOCK_DIR / "merged_recommendations.json"
WEEKLY_PATH = MOCK_DIR / "weekly_recommendations.json"
OUT_PATH = MOCK_DIR / "trading_data.json"


def _apply_position_to_holding(
    holding: dict[str, Any],
    position: dict[str, Any] | None,
) -> dict[str, Any]:
    """가상매수 포지션 → 카드 수익률·달성·에이전트 필드."""
    if position:
        holding.update(holding_fields_from_position(position))
    else:
        holding.update(holding_fields_from_position(None))
    return holding


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


def _rankings_from_holdings(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        holdings,
        key=lambda h: float(h.get("return_pct") if h.get("return_pct") is not None else -1e9),
        reverse=True,
    )
    return [
        {
            "name": h.get("name") or "",
            "buy_amount": h.get("buy_amount"),
            "eval_amount": h.get("eval_amount"),
            "return_pct": h.get("return_pct"),
        }
        for h in ordered
    ]


def _build_recommendation_card_index() -> dict[str, dict[str, Any]]:
    """ticker → merged 카드 (최신 파일 우선)."""
    paths: list[Path] = []
    if MERGED_PATH.is_file():
        paths.append(MERGED_PATH)
    mirror_dir = MOCK_DIR / "firebase_mirror"
    if mirror_dir.is_dir():
        paths.extend(sorted(mirror_dir.glob("weekly_*.json"), key=lambda p: p.stat().st_mtime))
    paths = sorted(
        {p.resolve() for p in paths if p.is_file()},
        key=lambda p: p.stat().st_mtime,
    )

    index: dict[str, dict[str, Any]] = {}
    for path in paths:
        data = _load_json(path)
        if path == MERGED_PATH:
            cards = data.get("merged_cards") or []
        else:
            cards = data.get("mergedRecommendations") or data.get("merged_cards") or []
        for card in cards:
            ticker = str(card.get("ticker", "")).zfill(6)
            if not ticker:
                continue
            enriched = (
                card
                if card.get("plainReason")
                else enrich_merged_card(card)
            )
            index[ticker] = enriched
    return index


def _card_current_price(card: dict[str, Any], fallback: int) -> int:
    current = card.get("current_price")
    try:
        return int(round(float(current))) if current is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _holding_from_position(
    position: dict[str, Any],
    card: dict[str, Any],
) -> dict[str, Any]:
    ticker = str(position.get("ticker", "")).zfill(6)
    buy = int(position.get("buyPrice") or 0)
    qty = max(1, int(position.get("quantity") or 1))
    invested = int(position.get("investedAmount") or buy * qty)
    cur = int(position.get("currentPrice") or buy)
    if card:
        cur = _card_current_price(card, cur)

    sector_key = str(card.get("sector_group") or "")
    sector_label = SECTOR_LABELS.get(sector_key, sector_key) if sector_key else "—"
    grok_warn = _grok_warnings(card) if card else []
    risks = list(card.get("risk_factors") or []) if card else []
    reasons = list(card.get("reasons_sample") or []) if card else []

    plain = (
        {
            "plainReason": card.get("plainReason"),
            "plainRisk": card.get("plainRisk"),
            "viewGuide": card.get("viewGuide"),
        }
        if card.get("plainReason")
        else (
            build_plain_copy(
                name=str(card.get("name") or position.get("name") or ""),
                reason_lines=reasons,
                risk_lines=risks,
                grok_validation=card.get("grok_validation"),
            )
            if card
            else {
                "plainReason": "—",
                "plainRisk": "—",
                "viewGuide": "—",
            }
        )
    )

    rec_agents = normalize_agent_names(
        list(position.get("recommendedAgents") or position.get("agentNames") or [])
        or list(card.get("recommending_agents") or [])
    )
    agent_keys = list(position.get("agentKeys") or card.get("agent_keys") or [])

    exec_snake = position_to_ui_snake(position)
    row: dict[str, Any] = {
        "ticker": ticker,
        "name": str(position.get("name") or card.get("name") or ""),
        "entry_type": exec_snake.get("entry_type") or "",
        "execution_market": exec_snake.get("execution_market") or "",
        "fallback_execution": exec_snake.get("fallback_execution"),
        "has_weekend_risk": exec_snake.get("has_weekend_risk"),
        "trigger_type": exec_snake.get("trigger_type") or "",
        "trigger_reason": exec_snake.get("trigger_reason") or [],
        "first_signal_at": exec_snake.get("first_signal_at"),
        "execution_at": exec_snake.get("execution_at"),
        "execution_price": exec_snake.get("execution_price"),
        "sector": sector_label,
        "sector_group": sector_key,
        "business_summary": sector_label,
        "buy_price": buy,
        "buy_amount": invested,
        "current_price": cur,
        "eval_amount": cur * qty,
        "price_status": "ok",
        "return_pct": float(position.get("currentReturnRate") or 0.0),
        "agent": ", ".join(rec_agents) if rec_agents else "—",
        "recommending_agents": rec_agents,
        "recommending_agents_full": rec_agents,
        "agent_keys": agent_keys,
        "recommendation_count": int(card.get("recommendation_count") or len(rec_agents) or 0),
        "consensus_label": card.get("consensus_label") or "",
        "selection_reason": _format_reasons(reasons, list(card.get("reasons_sample") or []))
        if card
        else "—",
        "risk_factors_text": _format_risks(risks, grok_warn) if card else "—",
        "risk_factors": risks,
        "plain_reason": plain["plainReason"],
        "plain_risk": plain["plainRisk"],
        "view_guide": plain["viewGuide"],
        "grok_warnings": grok_warn,
        "entry_range": card.get("entry_range") if card else None,
        "target_price": card.get("target_price") if card else None,
        "grok_validation": card.get("grok_validation") if card else None,
        "virtually_bought": True,
    }
    row.update(holding_fields_from_position(position))
    row["buy_amount"] = invested
    row["eval_amount"] = int(row.get("eval_amount") or cur * qty)
    row["current_price"] = cur
    if buy > 0:
        row["return_pct"] = round((cur - buy) / buy * 100.0, 4)
    return row


def build_cumulative_trading_payload(
    *,
    data_source: str = "virtualPositions/ledger",
) -> dict[str, Any]:
    """전 주차 누적 가상매수·성과 (특정 week_id 화면·필터 없음)."""
    sync_ledger_from_all_stored_weeks()
    card_index = _build_recommendation_card_index()

    positions = list_positions()
    price_map: dict[str, int] = {}
    for pos in positions:
        ticker = str(pos.get("ticker", "")).zfill(6)
        if not ticker:
            continue
        card = card_index.get(ticker) or {}
        fallback = int(pos.get("currentPrice") or pos.get("buyPrice") or 0)
        price_map[ticker] = _card_current_price(card, fallback) if card else fallback
    if price_map:
        refresh_position_prices(price_map)
        positions = list_positions()

    perf_map = recompute_and_persist().get("agents") or {}
    holdings = [
        _holding_from_position(pos, card_index.get(str(pos.get("ticker", "")).zfill(6), {}))
        for pos in positions
    ]
    holdings.sort(
        key=lambda h: float(h.get("return_pct") if h.get("return_pct") is not None else -1e9),
        reverse=True,
    )

    weekly: dict[str, Any] = {}
    if WEEKLY_PATH.is_file():
        weekly = _load_json(WEEKLY_PATH)

    agents_panel = agent_panel_rows(perf_map)
    for row in agents_panel:
        spec_agent = next(
            (a for a in (weekly.get("agents") or []) if a.get("agent_key") == row["agent_key"]),
            None,
        )
        if spec_agent:
            row["model_id"] = spec_agent.get("model_id") or ""
            names = [
                str(r.get("name") or "")
                for r in (spec_agent.get("recommendations") or [])
                if r.get("name")
            ]
            row["pick_names"] = names

    now = datetime.now(KST)
    return {
        "pageMeta": {
            "title": "모의 투자 시스템",
            "market": "한국시장",
            "updated_at": now.strftime("%H:%M 업데이트"),
            "data_source": data_source,
            "position_count": len(holdings),
        },
        "scope": "cumulative",
        "holdings": holdings,
        "rankings": _rankings_from_holdings(holdings),
        "agents": agents_panel,
        "agentPerformance": list(perf_map.values()),
        "excluded_candidates": [],
    }


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
    data_source: str = "merged_recommendations.json",
    week_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    picks = _aggregate_picks_by_ticker(weekly)

    week_id = merged.get("week_id") or weekly.get("week_id") or ""
    generated_at = merged.get("generated_at") or weekly.get("generated_at") or ""
    cards = merged.get("merged_cards") or []

    if week_doc:
        import_from_week_doc(str(week_id), week_doc)

    week_positions = positions_by_week(str(week_id))
    price_map = {
        t: int(p.get("currentPrice") or p.get("buyPrice") or 0)
        for t, p in week_positions.items()
    }
    if price_map:
        refresh_position_prices(price_map, week_id=str(week_id))
        week_positions = positions_by_week(str(week_id))

    perf_map = recompute_and_persist().get("agents") or {}

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

        rec_agents = normalize_agent_names(list(card_plain.get("recommending_agents") or []))
        row = {
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
            "recommending_agents": rec_agents,
            "recommending_agents_full": rec_agents,
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
            "grok_validation": card_plain.get("grok_validation"),
            "virtually_bought": ticker in week_positions,
        }
        _apply_position_to_holding(row, week_positions.get(ticker))
        holdings.append(row)

    agents_panel = agent_panel_rows(perf_map)
    for row in agents_panel:
        spec_agent = next(
            (a for a in (weekly.get("agents") or []) if a.get("agent_key") == row["agent_key"]),
            None,
        )
        if spec_agent:
            row["model_id"] = spec_agent.get("model_id") or ""
            names = [
                str(r.get("name") or "")
                for r in (spec_agent.get("recommendations") or [])
                if r.get("name")
            ]
            row["pick_names"] = names

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
        "agentPerformance": list(perf_map.values()),
        "excluded_candidates": [],
    }
    return payload


def build_trading_data(
    *,
    out_path: Path = OUT_PATH,
) -> dict[str, Any]:
    payload = build_cumulative_trading_payload(
        data_source="virtualPositions/ledger+local_mirror",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def build_trading_data_from_firestore_doc(
    firestore_doc: dict[str, Any],
) -> dict[str, Any]:
    week_id = str(firestore_doc.get("weekId") or firestore_doc.get("week_id") or "")
    if week_id:
        import_from_week_doc(week_id, firestore_doc)
    source = firestore_doc.get("persist_backend") or "firestore"
    path = firestore_doc.get("firestore_path") or "weeklyRecommendations"
    return build_cumulative_trading_payload(data_source=f"{source}:{path}")
