"""Trading calendar helpers for SIMPLE_REPLAY."""

from __future__ import annotations

from src.trading.competition.replay import data_provider
from src.trading.simple_replay.errors import SimpleReplayError


def normalize_yyyymmdd(value: str) -> str:
    raw = value.strip().replace("-", "")
    if len(raw) != 8 or not raw.isdigit():
        raise SimpleReplayError("invalid_decision_date", detail=value)
    return raw


def resolve_schedule(decision_date: str, observation_days: int) -> dict[str, object]:
    """Return buy_date (next session) and evaluation_dates (observation_days closes from buy_date)."""
    decision_date = normalize_yyyymmdd(decision_date)
    buy_date, _, errs = data_provider.next_trading_date_after(decision_date)
    if not buy_date:
        raise SimpleReplayError("buy_date_unavailable", detail=";".join(errs[:3]))

    end_probe = (
        __import__("datetime").datetime.strptime(buy_date, "%Y%m%d")
        + __import__("datetime").timedelta(days=observation_days * 3 + 14)
    ).strftime("%Y%m%d")
    cal = data_provider.list_trading_dates_result(buy_date, end_probe)
    sessions = cal.get("dates") or []
    if not sessions:
        raise SimpleReplayError("evaluation_calendar_unavailable", detail=str(cal.get("errors")))

    evaluation_dates = sessions[:observation_days]
    if len(evaluation_dates) < observation_days:
        raise SimpleReplayError(
            "insufficient_evaluation_sessions",
            detail=f"need={observation_days} got={len(evaluation_dates)}",
        )

    return {
        "decision_date": decision_date,
        "buy_date": buy_date,
        "evaluation_dates": evaluation_dates,
        "calendar_source": cal.get("primary_source"),
    }
