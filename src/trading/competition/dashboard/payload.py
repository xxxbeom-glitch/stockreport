"""Dashboard payload builder (spec §12)."""

from __future__ import annotations

from typing import Any

from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS, TEAM_META, TEAM_TO_AGENT
from src.trading.competition.execution.accounting import load_snapshots
from src.trading.competition.storage.accounts import load_all_accounts
from src.trading.competition.storage.journal import load_notifications, load_trades
from src.trading.competition.storage.positions import load_all_positions

AGENT_TO_TEAM = {v: k for k, v in TEAM_TO_AGENT.items()}


def _load_weekly_reports() -> dict[str, Any]:
    from src.trading.competition.ops.weekly_report import load_weekly_reports_for_dashboard

    return load_weekly_reports_for_dashboard()


def _return_pct(initial: int, current: int) -> float:
    if initial <= 0:
        return 0.0
    return round((current - initial) / initial * 100, 2)


def build_dashboard_payload() -> dict[str, Any]:
    accounts = load_all_accounts()
    positions = load_all_positions()
    trades = load_trades()
    notifications = load_notifications()
    snapshots = load_snapshots()

    cash_total = sum(acc.cash_krw for acc in accounts.values())
    asset_total = sum(acc.total_assets_krw for acc in accounts.values())

    agent_meta: dict[str, Any] = {}
    timeline_series: list[dict[str, Any]] = []
    stock_catalog: dict[str, Any] = {}
    trade_history: dict[str, list] = {f"agent{i}": [] for i in range(1, 5)}

    best_team_return = -999.0
    best_team_key = "agent1"
    best_stock_return = -999.0
    best_stock_name = "-"

    for tid in TEAM_IDS:
        agent_key = TEAM_TO_AGENT[tid]
        meta = TEAM_META[tid]
        acc = accounts.get(tid)
        tp = positions.get(tid)
        initial = acc.initial_cash_krw if acc else INITIAL_CASH_KRW
        total = acc.total_assets_krw if acc else initial
        cash = acc.cash_krw if acc else initial
        ret = _return_pct(initial, total)
        if ret > best_team_return:
            best_team_return = ret
            best_team_key = agent_key

        agent_meta[agent_key] = {
            "name": meta["display_name"],
            "badge": meta["type_label"],
            "badgeClass": meta["badge_class"],
            "strategy": meta["strategy_label"],
            "cashKrw": cash,
            "totalAssetsKrw": total,
            "returnPct": ret,
            "status": acc.status if acc else "active",
        }

        team_snaps = [s for s in snapshots if s.get("team_id") == tid]
        timeline_series.append(
            {
                "key": agent_key,
                "label": meta["display_name"],
                "color": ["#4f8cff", "#34c759", "#ff9500", "#af52de"][TEAM_IDS.index(tid)],
                "data": [s.get("total_assets_krw", initial) for s in team_snaps]
                or [initial, total],
            }
        )

        if tp:
            for pos in tp.positions:
                if pos.quantity <= 0:
                    continue
                if pos.eval_return_pct > best_stock_return:
                    best_stock_return = pos.eval_return_pct
                    best_stock_name = pos.name
                code = pos.ticker
                if code not in stock_catalog:
                    block = {
                        "avg": pos.avg_price_krw,
                        "current": pos.current_price_krw,
                        "returnPct": pos.eval_return_pct,
                        "pnl": pos.eval_pnl_krw,
                    }
                    stock_catalog[code] = {
                        "name": pos.name,
                        "agents": [],
                        "reason": pos.buy_reason_label,
                        "all": block,
                        "7d": dict(block),
                        "14d": dict(block),
                    }
                stock_catalog[code]["agents"].append(agent_key)

    labels = []
    if snapshots:
        labels = sorted({s.get("captured_at", "")[:10] for s in snapshots if s.get("captured_at")})
    if not labels:
        labels = ["start"]

    for i, tr in enumerate(trades):
        tid = tr.get("team_id", "A")
        agent_key = TEAM_TO_AGENT.get(tid, "agent1")
        side = tr.get("side", "buy")
        trade_history[agent_key].append(
            {
                "dayIndex": min(i, max(len(labels) - 1, 0)),
                "date": (tr.get("executed_at") or "")[:10],
                "name": tr.get("name"),
                "code": tr.get("ticker"),
                "side": "sell" if "sell" in str(side) else "buy",
                "price": tr.get("fill_price_krw"),
                "qty": tr.get("quantity"),
                "pnl": tr.get("realized_pnl_krw"),
                "reason": tr.get("reason_label"),
            }
        )

    notif_ui = [
        {
            "id": n.get("notification_id"),
            "category": n.get("category"),
            "type": n.get("category"),
            "title": n.get("title"),
            "sub": n.get("sub"),
            "time": n.get("created_at"),
            "read": n.get("read", False),
            "navigate": n.get("navigate"),
        }
        for n in notifications[-50:]
    ]

    return {
        "dataSource": "live",
        "cashAmount": cash_total,
        "totalAssets": asset_total,
        "bestAgentKey": best_team_key,
        "bestAgentReturnPct": best_team_return,
        "bestStockName": best_stock_name,
        "bestStockReturnPct": best_stock_return,
        "timeline": {"labels": labels, "series": timeline_series},
        "agentMeta": agent_meta,
        "stockCatalog": stock_catalog,
        "tradeHistory": trade_history,
        "notifications": notif_ui,
        "weeklyReports": _load_weekly_reports(),
        "operatingDays": max(len(labels), 1),
        "teams": {tid: agent_meta[TEAM_TO_AGENT[tid]] for tid in TEAM_IDS},
    }
