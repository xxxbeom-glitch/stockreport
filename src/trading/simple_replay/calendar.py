"""Trading calendar helpers for SIMPLE_REPLAY."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.trading.competition.replay import data_provider
from src.trading.simple_replay.constants import EVALUATION_HORIZONS, UI_EVALUATION_HORIZON
from src.trading.simple_replay.errors import SimpleReplayError


def normalize_yyyymmdd(value: str) -> str:
    raw = value.strip().replace("-", "")
    if len(raw) != 8 or not raw.isdigit():
        raise SimpleReplayError("invalid_decision_date", detail=value)
    return raw


def _horizon_status(available: int, target: int) -> str:
    if available >= target:
        return "complete"
    if available > 0:
        return "evaluation_pending"
    return "insufficient_future_data"


def resolve_schedule(decision_date: str, observation_days: int = UI_EVALUATION_HORIZON) -> dict[str, object]:
    """
    buy_date = next session after decision_date.
    evaluation_horizons: 5 / 10 / 20 trading-day closes from buy_date (JSON-ready).
    evaluation_dates = UI default horizon (5).
    """
    decision_date = normalize_yyyymmdd(decision_date)
    buy_date, _, errs = data_provider.next_trading_date_after(decision_date)
    if not buy_date:
        raise SimpleReplayError("buy_date_unavailable", detail=";".join(errs[:3]))

    max_horizon = max(EVALUATION_HORIZONS)
    end_probe = (
        datetime.strptime(buy_date, "%Y%m%d") + timedelta(days=max_horizon * 3 + 21)
    ).strftime("%Y%m%d")
    cal = data_provider.list_trading_dates_result(buy_date, end_probe)
    sessions = cal.get("dates") or []
    if not sessions:
        raise SimpleReplayError("evaluation_calendar_unavailable", detail=str(cal.get("errors")))

    evaluation_horizons: dict[str, dict[str, object]] = {}
    for h in EVALUATION_HORIZONS:
        slice_dates = sessions[:h]
        evaluation_horizons[str(h)] = {
            "horizon_days": h,
            "dates": slice_dates,
            "status": _horizon_status(len(slice_dates), h),
            "last_date": slice_dates[-1] if slice_dates else None,
        }

    ui_dates = list(evaluation_horizons[str(UI_EVALUATION_HORIZON)].get("dates") or [])
    if len(ui_dates) < observation_days:
        raise SimpleReplayError(
            "insufficient_evaluation_sessions",
            detail=f"need={observation_days} got={len(ui_dates)}",
        )

    return {
        "decision_date": decision_date,
        "buy_date": buy_date,
        "evaluation_dates": ui_dates,
        "evaluation_horizons": evaluation_horizons,
        "observation_days_ui": UI_EVALUATION_HORIZON,
        "calendar_source": cal.get("primary_source"),
    }
