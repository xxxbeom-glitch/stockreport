"""Team D rebound scout filters — pullback alone is insufficient."""

from __future__ import annotations

from typing import Any

# Pullback window (spec: 눌림 구간)
D_MAX_CHANGE_PCT = -2.0
D_MIN_CHANGE_PCT = -12.0

# Minimum liquidity for D candidates
D_MIN_AVG_TV = 2_500_000_000

# Rebound / stabilization thresholds
D_MIN_TV_RECOVERY_RATIO = 1.0
D_MIN_REBOUND_FROM_LOW_PCT = 1.5
D_MIN_CHANGE_IMPROVEMENT_PCT = 1.0
D_MIN_FOREIGN_NET = 1

BLOCKED_RISK_STATUSES = frozenset(
    {"halt", "managed", "liquidation", "risk", "warning"}
)

STRUCTURAL_BAD_EVENT_TYPES = frozenset(
    {
        "DISCLOSURE_NEGATIVE",
        "DISCLOSURE_RISK",
        "RISK_ALERT",
        "POSITION_RISK_ALERT",
        "NEWS_NEGATIVE",
    }
)


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = row.get(key)
    if val is None:
        metrics = row.get("metrics") or {}
        val = metrics.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _change_rate(row: dict[str, Any]) -> float:
    return _f(row, "change_rate_pct")


def _tv_ratio(row: dict[str, Any]) -> float:
    if row.get("tv_ratio_20d") is not None:
        return _f(row, "tv_ratio_20d")
    avg = _f(row, "avg_trading_value_20d_krw")
    cur = _f(row, "current_trading_value_krw")
    if avg > 0 and cur > 0:
        return cur / avg
    return 0.0


def _risk_status(row: dict[str, Any]) -> str:
    return str(row.get("risk_status") or (row.get("metrics") or {}).get("risk_status") or "normal")


def has_rebound_or_stabilization_signal(row: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Require at least one recovery clue beyond mere decline.
    """
    signals: list[str] = []
    change = _change_rate(row)
    tv_r = _tv_ratio(row)
    rebound_low = _f(row, "rebound_from_low_pct")
    prior_change = _f(row, "prior_change_pct", change - 2.0)
    foreign = _f(row, "foreign_net")

    if tv_r >= D_MIN_TV_RECOVERY_RATIO:
        signals.append(f"tv_recovery_{tv_r:.1f}x")
    if rebound_low >= D_MIN_REBOUND_FROM_LOW_PCT:
        signals.append(f"rebound_low_{rebound_low:.1f}pct")
    if change > prior_change + D_MIN_CHANGE_IMPROVEMENT_PCT:
        signals.append(f"stabilizing_{prior_change:.1f}_to_{change:.1f}")
    if foreign >= D_MIN_FOREIGN_NET:
        signals.append(f"foreign_net_{int(foreign)}")

    return bool(signals), signals


def is_risk_blocked(row: dict[str, Any], *, blocked_tickers: set[str] | None = None) -> tuple[bool, str]:
    ticker = str(row.get("ticker", "")).zfill(6)
    if blocked_tickers and ticker in blocked_tickers:
        return True, "blocked_ticker_risk_or_bad_news"

    status = _risk_status(row)
    if status in BLOCKED_RISK_STATUSES:
        return True, f"risk_status_{status}"

    if row.get("exclude_new_entry"):
        return True, "exclude_new_entry"

    notes = row.get("risk_notes") or []
    if isinstance(notes, list):
        joined = " ".join(str(n) for n in notes)
        for kw in ("거래정지", "관리종목", "정리매매", "상장폐지"):
            if kw in joined:
                return True, f"risk_note_{kw}"

    return False, ""


def evaluate_d_candidate(
    row: dict[str, Any],
    *,
    blocked_tickers: set[str] | None = None,
) -> tuple[bool, str, list[str]]:
    """
    Returns (eligible, reject_reason, rebound_signals).
    Simple drop-only setups are rejected.
    """
    change = _change_rate(row)
    avg_tv = _f(row, "avg_trading_value_20d_krw")

    if not (D_MIN_CHANGE_PCT <= change <= D_MAX_CHANGE_PCT):
        return False, "outside_pullback_window", []

    if avg_tv < D_MIN_AVG_TV:
        return False, "insufficient_liquidity", []

    blocked, reason = is_risk_blocked(row, blocked_tickers=blocked_tickers)
    if blocked:
        return False, reason, []

    has_signal, signals = has_rebound_or_stabilization_signal(row)
    if not has_signal:
        return False, "drop_without_rebound_signal", []

    # Deep drop requires stronger recovery evidence
    if change <= -8.0:
        strong = any(
            s.startswith("rebound_low_") or s.startswith("tv_recovery_")
            for s in signals
        )
        if not strong:
            return False, "deep_drop_needs_stronger_rebound", signals

    return True, "", signals


def collect_blocked_d_tickers(
    actionable_events: list[dict[str, Any]] | None = None,
) -> set[str]:
    """Tickers with structural bad news from actionable events."""
    blocked: set[str] = set()
    for evt in actionable_events or []:
        et = str(evt.get("event_type") or "")
        direction = str(evt.get("direction") or "")
        if et in STRUCTURAL_BAD_EVENT_TYPES or direction == "NEGATIVE":
            if evt.get("importance") in ("HIGH", "CRITICAL", "MEDIUM"):
                blocked.update(evt.get("direct_tickers") or [])
    return blocked
