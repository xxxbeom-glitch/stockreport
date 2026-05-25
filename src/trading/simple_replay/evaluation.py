"""Five trading-day close evaluation after virtual buy."""

from __future__ import annotations

from typing import Any

from src.trading.competition.replay.market_data import close_price_krw
from src.trading.simple_replay.errors import SimpleReplayError


def evaluate_position(
    position: dict[str, Any],
    evaluation_dates: list[str],
) -> dict[str, Any]:
    ticker = position["ticker"]
    buy_price = int(position["buy_price"])
    qty = int(position["quantity"])
    target = float(position.get("target_price") or 0)

    daily: list[dict[str, Any]] = []
    returns: list[float] = []
    target_reached_date = None

    for d in evaluation_dates:
        close, err = close_price_krw(ticker, d)
        if not close or close <= 0:
            raise SimpleReplayError("evaluation_price_missing", detail=f"{ticker}:{d}:{err}")
        mv = close * qty
        pnl = (close - buy_price) * qty
        ret = round((close - buy_price) / buy_price * 100, 2) if buy_price else 0.0
        reached = target > 0 and close >= target
        if reached and not target_reached_date:
            target_reached_date = d
        daily.append(
            {
                "date": d,
                "close_price": close,
                "market_value": mv,
                "unrealized_pnl": pnl,
                "return_pct": ret,
                "target_reached": reached,
            }
        )
        returns.append(ret)

    final_ret = returns[-1] if returns else 0.0
    return {
        **position,
        "daily_evaluations": daily,
        "highest_return_pct": max(returns) if returns else 0.0,
        "lowest_return_pct": min(returns) if returns else 0.0,
        "final_return_pct": final_ret,
        "target_reached_date": target_reached_date,
        "final_close_price": daily[-1]["close_price"] if daily else 0,
        "final_unrealized_pnl": daily[-1]["unrealized_pnl"] if daily else 0,
    }


def team_totals(
    team_id: str,
    *,
    position: dict[str, Any] | None,
    skip: bool,
) -> dict[str, Any]:
    from src.trading.simple_replay.constants import INITIAL_CASH_KRW

    if skip or not position:
        return {
            "team_id": team_id,
            "cash": INITIAL_CASH_KRW,
            "holding_market_value": 0,
            "total_asset": INITIAL_CASH_KRW,
            "cumulative_return_pct": 0.0,
        }
    cash = int(position.get("remaining_cash") or 0)
    mv = int(position["daily_evaluations"][-1]["market_value"]) if position.get("daily_evaluations") else 0
    total = cash + mv
    ret = round((total - INITIAL_CASH_KRW) / INITIAL_CASH_KRW * 100, 2)
    return {
        "team_id": team_id,
        "cash": cash,
        "holding_market_value": mv,
        "total_asset": total,
        "cumulative_return_pct": ret,
    }


def build_timeline(
    evaluation_dates: list[str],
    team_snapshots: dict[str, list[int]],
) -> dict[str, Any]:
    """One total_asset point per evaluation session close."""
    from src.trading.simple_replay.constants import AGENT_UI, TEAM_IDS

    labels = [f"{d[:4]}.{d[4:6]}.{d[6:8]}" for d in evaluation_dates]
    colors = ["#4f8cff", "#34c759", "#ff9500", "#af52de"]
    series = []
    for i, tid in enumerate(TEAM_IDS):
        ui = AGENT_UI[tid]
        series.append(
            {
                "key": ui["agent_key"],
                "label": ui["display_name"],
                "color": colors[i],
                "data": team_snapshots.get(tid, []),
            }
        )
    return {"labels": labels, "series": series}
