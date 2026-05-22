# -*- coding: utf-8 -*-
"""매수가 대비 수익률·최고/최저·+10%/+20% 최초 달성 기록 (매도·종료 없음)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def return_pct(buy_price: int, current_price: int) -> float:
    if buy_price <= 0:
        return 0.0
    return (current_price - buy_price) / buy_price * 100.0


def days_since_buy(bought_at: str, *, now: datetime | None = None) -> int:
    """매수 당일=0, 다음날=1 (달력일 기준)."""
    now = now or datetime.now(KST)
    try:
        bought = datetime.fromisoformat(str(bought_at).replace("Z", "+00:00"))
        if bought.tzinfo is None:
            bought = bought.replace(tzinfo=KST)
        else:
            bought = bought.astimezone(KST)
    except ValueError:
        return 0
    return max(0, (now.astimezone(KST).date() - bought.date()).days)


def apply_price_observation(
    position: dict[str, Any],
    current_price: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """현재가 반영 + 최고/최저 + 마일스톤 (한 번 달성한 기록은 유지)."""
    now = now or datetime.now(KST)
    buy = int(position.get("buyPrice") or position.get("buy_price") or 0)
    if buy <= 0:
        return position

    qty = max(1, int(position.get("quantity") or 1))
    cur = int(current_price)
    invested = int(position.get("investedAmount") or buy * qty)
    eval_amount = cur * qty
    pl = eval_amount - invested
    rate = round(return_pct(buy, cur), 4)

    high = int(position.get("highestPriceSinceBuy") or buy)
    low = int(position.get("lowestPriceSinceBuy") or buy)
    if cur > high:
        high = cur
    if cur < low:
        low = cur

    position["quantity"] = qty
    position["investedAmount"] = invested
    position["currentPrice"] = cur
    position["currentReturnRate"] = rate
    position["currentProfitLoss"] = pl
    position["highestPriceSinceBuy"] = high
    position["highestReturnRateSinceBuy"] = round(return_pct(buy, high), 4)
    position["lowestPriceSinceBuy"] = low
    position["lowestReturnRateSinceBuy"] = round(return_pct(buy, low), 4)
    position["updatedAt"] = now.isoformat(timespec="seconds")

    elapsed = days_since_buy(str(position.get("boughtAt") or position.get("bought_at") or ""), now=now)

    if rate >= 10.0 and not position.get("reached10Percent"):
        position["reached10Percent"] = True
        position["reached10PercentAt"] = now.isoformat(timespec="seconds")
        position["daysTo10Percent"] = elapsed

    if rate >= 20.0 and not position.get("reached20Percent"):
        position["reached20Percent"] = True
        position["reached20PercentAt"] = now.isoformat(timespec="seconds")
        position["daysTo20Percent"] = elapsed

    return position


# 하위 호환
apply_milestone_updates = apply_price_observation


def holding_fields_from_position(position: dict[str, Any] | None) -> dict[str, Any]:
    """kr_trading 카드·API용 필드."""
    if not position:
        return {
            "virtually_bought": False,
            "reached10Percent": False,
            "reached10PercentAt": None,
            "daysTo10Percent": None,
            "reached20Percent": False,
            "reached20PercentAt": None,
            "daysTo20Percent": None,
            "milestone_10_days": None,
            "milestone_20_days": None,
        }

    agents = list(position.get("recommendedAgents") or position.get("agentNames") or [])
    qty = max(1, int(position.get("quantity") or 1))
    buy = int(position.get("buyPrice") or 0)
    cur = int(position.get("currentPrice") or buy)
    invested = int(position.get("investedAmount") or buy * qty)
    eval_amount = cur * qty
    rate = float(position.get("currentReturnRate") or 0.0)
    d10 = position.get("daysTo10Percent")
    d20 = position.get("daysTo20Percent")

    return {
        "virtually_bought": True,
        "bought_at": position.get("boughtAt"),
        "buy_price": buy,
        "buy_amount": invested,
        "quantity": qty,
        "invested_amount": invested,
        "current_price": cur,
        "eval_amount": eval_amount,
        "return_pct": rate,
        "current_return_rate": rate,
        "current_profit_loss": int(position.get("currentProfitLoss") or eval_amount - invested),
        "highest_price_since_buy": position.get("highestPriceSinceBuy"),
        "highest_return_rate_since_buy": position.get("highestReturnRateSinceBuy"),
        "lowest_price_since_buy": position.get("lowestPriceSinceBuy"),
        "lowest_return_rate_since_buy": position.get("lowestReturnRateSinceBuy"),
        "reached10Percent": bool(position.get("reached10Percent")),
        "reached10PercentAt": position.get("reached10PercentAt"),
        "daysTo10Percent": d10,
        "reached20Percent": bool(position.get("reached20Percent")),
        "reached20PercentAt": position.get("reached20PercentAt"),
        "daysTo20Percent": d20,
        "milestone_10_days": d10,
        "milestone_20_days": d20,
        "recommended_agents": agents,
        "recommending_agents": agents,
        "recommending_agents_full": agents,
        "agent": ", ".join(agents) if agents else "—",
    }


def milestone_fields_for_ui(position: dict[str, Any] | None) -> dict[str, Any]:
    row = holding_fields_from_position(position)
    return {
        k: row[k]
        for k in (
            "virtually_bought",
            "reached10Percent",
            "reached10PercentAt",
            "daysTo10Percent",
            "reached20Percent",
            "reached20PercentAt",
            "daysTo20Percent",
            "milestone_10_days",
            "milestone_20_days",
        )
    }
