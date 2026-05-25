"""Build baseline dashboard payload from SIMPLE_REPLAY results."""

from __future__ import annotations

from typing import Any

from src.trading.simple_replay.constants import (
    AGENT_UI,
    INITIAL_CASH_KRW,
    TEAM_IDS,
    TEAM_TO_AGENT,
    TOTAL_SEED_KRW,
)


def _return_pct(initial: int, current: int) -> float:
    if initial <= 0:
        return 0.0
    return round((current - initial) / initial * 100, 2)


def build_dashboard_payload(
    *,
    run_id: str,
    manifest: dict[str, Any],
    decisions: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    team_totals: dict[str, dict[str, Any]],
    timeline: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    agent_meta: dict[str, Any] = {}
    stock_catalog: dict[str, Any] = {}
    trade_history: dict[str, list] = {f"agent{i}": [] for i in range(1, 5)}

    best_team_return = -999.0
    best_team_key = "agent1"
    best_stock_return = -999.0
    best_stock_name = "-"

    pos_by_team = {p["team_id"]: p for p in positions}

    for tid in TEAM_IDS:
        ui = AGENT_UI[tid]
        key = ui["agent_key"]
        totals = team_totals[tid]
        ret = float(totals.get("cumulative_return_pct") or 0)
        if ret > best_team_return:
            best_team_return = ret
            best_team_key = key

        agent_meta[key] = {
            "name": ui["display_name"],
            "badge": ui["type_label"],
            "badgeClass": ui["badge_class"],
            "strategy": ui["strategy_label"],
            "cashKrw": totals.get("cash", INITIAL_CASH_KRW),
            "totalAssetsKrw": totals.get("total_asset", INITIAL_CASH_KRW),
            "returnPct": ret,
            "status": "active",
        }

        pos = pos_by_team.get(tid)
        if pos and pos.get("daily_evaluations"):
            final = pos["daily_evaluations"][-1]
            code = pos["ticker"]
            if final["return_pct"] > best_stock_return:
                best_stock_return = final["return_pct"]
                best_stock_name = pos.get("name") or code
            block = {
                "avg": pos["buy_price"],
                "current": final["close_price"],
                "returnPct": final["return_pct"],
                "pnl": final["unrealized_pnl"],
            }
            stock_catalog[code] = {
                "name": pos.get("name") or code,
                "agents": [key],
                "reason": pos.get("reason_label") or "-",
                "all": block,
                "7d": block,
                "14d": block,
            }

    for dec in decisions:
        if dec.get("action") != "BUY":
            continue
        pos = pos_by_team.get(dec["team_id"])
        if not pos:
            continue
        key = TEAM_TO_AGENT[dec["team_id"]]
        bd = pos.get("buy_date") or manifest.get("buy_date")
        trade_history[key].append(
            {
                "dayIndex": 0,
                "date": f"{bd[:4]}-{bd[4:6]}-{bd[6:8]}" if bd and len(bd) == 8 else bd,
                "name": pos.get("name"),
                "code": pos.get("ticker"),
                "side": "buy",
                "price": pos.get("buy_price"),
                "qty": pos.get("quantity"),
                "pnl": None,
                "reason": dec.get("reason_label"),
            }
        )

    cash_total = sum(team_totals[t]["cash"] for t in TEAM_IDS)
    asset_total = sum(team_totals[t]["total_asset"] for t in TEAM_IDS)
    seed_ret = _return_pct(TOTAL_SEED_KRW, asset_total)

    tied = [t for t in TEAM_IDS if team_totals[t]["cumulative_return_pct"] == best_team_return]
    if len(tied) > 1:
        best_agent_sub = f"공동 1위 · {len(tied)}개 팀"
    else:
        best_agent_sub = f"{AGENT_UI[tied[0]]['display_name']} · {AGENT_UI[tied[0]]['strategy_label']}"

    if best_stock_name == "-" or best_stock_return <= -999:
        best_stock_main = "-"
        best_stock_sub = "추천 종목 없음"
    else:
        best_stock_main = f"{best_stock_return:+.2f}%"
        holder = next(
            (p for p in positions if p.get("name") == best_stock_name or p.get("ticker") == best_stock_name),
            None,
        )
        holder_team = AGENT_UI[holder["team_id"]]["display_name"] if holder else ""
        best_stock_sub = f"{best_stock_name} · {holder_team}"

    decision_date = manifest.get("decision_date", "")
    dd_label = (
        f"{decision_date[:4]}.{decision_date[4:6]}.{decision_date[6:8]}"
        if len(str(decision_date)) == 8
        else decision_date
    )

    return {
        "dataSource": "simple_replay",
        "simpleReplayRunId": run_id,
        "cashAmount": cash_total,
        "totalAssets": asset_total,
        "totalSeedKrw": TOTAL_SEED_KRW,
        "portfolioReturnPct": seed_ret,
        "bestAgentKey": best_team_key,
        "bestAgentReturnPct": best_team_return if best_team_return > -999 else 0,
        "bestAgentSub": best_agent_sub,
        "bestStockName": best_stock_name if best_stock_name != "-" else "-",
        "bestStockReturnPct": best_stock_return if best_stock_return > -999 else 0,
        "bestStockSub": best_stock_sub,
        "timeline": timeline,
        "agentMeta": agent_meta,
        "stockCatalog": stock_catalog,
        "tradeHistory": trade_history,
        "weeklyReports": {"sr1": report},
        "operatingDays": len(manifest.get("evaluation_dates") or []),
        "notifications": manifest.get("notifications") or [],
        "simpleReplayMeta": {
            "runId": run_id,
            "decisionDate": decision_date,
            "decisionDateLabel": dd_label,
            "buyDate": manifest.get("buy_date"),
            "evaluationDates": manifest.get("evaluation_dates"),
            "evaluationHorizons": manifest.get("evaluation_horizons"),
            "observationDays": manifest.get("observation_days"),
            "status": "completed",
            "costModelApplied": manifest.get("cost_model_applied", False),
            "factsMeta": manifest.get("facts_meta"),
        },
        "headerMeta": (
            f"추천 기준일 {dd_label} · 초기 시드 에이전트별 500,000원 · SIMPLE REPLAY 완료"
        ),
    }
