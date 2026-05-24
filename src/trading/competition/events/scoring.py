"""Rule-based importance scoring for actionable event gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.trading.competition.events.models import RawSignal

# Pass threshold (0–100)
ACTIONABLE_SCORE_THRESHOLD = 55

# Per-scan caps (actionable events)
MAX_ACTIONABLE_PER_TICKER_ELIGIBLE = 2
MAX_ACTIONABLE_NEWS_PER_TICKER_ELIGIBLE = 1
MAX_ACTIONABLE_PER_TICKER_POSITION = 5

# Market reaction thresholds
MARKET_REACTION_CHANGE_PCT = 3.0
MARKET_REACTION_STRONG_CHANGE_PCT = 5.0
MARKET_REACTION_TV_RATIO = 1.8

NEWS_MATERIAL_KEYWORDS = (
    "실적",
    "잠정",
    "계약",
    "수주",
    "공급",
    "승인",
    "허가",
    "인수",
    "합병",
    "투자",
    "급등",
    "급락",
    "상한가",
    "하한가",
    "목표가",
    "신규",
    "특허",
    "FDA",
    "조사",
    "횡령",
    "분식",
    "거래정지",
    "관리종목",
    "상장폐지",
    "소송",
    "유상증자",
)

AUTO_PASS_TYPES = frozenset(
    {
        "POSITION_RISK_ALERT",
        "TRADING_STATUS_CHANGE",
    }
)

POSITION_HIGH_PRIORITY_TYPES = frozenset(
    {
        "POSITION_RISK_ALERT",
        "TRADING_STATUS_CHANGE",
        "DISCLOSURE_RISK",
    }
)


@dataclass
class GateScore:
    total: int
    auto_pass: bool
    market_reaction_confirmed: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def passes_threshold(self) -> bool:
        return self.auto_pass or self.total >= ACTIONABLE_SCORE_THRESHOLD


def _market_metrics(signal: RawSignal) -> dict[str, Any]:
    return dict(signal.metrics or {})


def has_market_reaction(signal: RawSignal) -> tuple[bool, list[str]]:
    m = _market_metrics(signal)
    reasons: list[str] = []
    change = m.get("change_rate_pct")
    tv_ratio = m.get("tv_ratio_20d")

    if change is not None:
        try:
            c = float(change)
            if abs(c) >= MARKET_REACTION_STRONG_CHANGE_PCT:
                reasons.append(f"strong_price_move:{c:+.1f}%")
            elif abs(c) >= MARKET_REACTION_CHANGE_PCT:
                reasons.append(f"price_move:{c:+.1f}%")
        except (TypeError, ValueError):
            pass

    if tv_ratio is not None:
        try:
            r = float(tv_ratio)
            if r >= MARKET_REACTION_TV_RATIO:
                reasons.append(f"tv_ratio:{r:.1f}x")
        except (TypeError, ValueError):
            pass

    return bool(reasons), reasons


def _news_has_material_keyword(signal: RawSignal) -> bool:
    text = f"{signal.summary} {signal.evidence.title}".lower()
    return any(kw.lower() in text or kw in signal.summary for kw in NEWS_MATERIAL_KEYWORDS)


def score_signal(signal: RawSignal) -> GateScore:
    """Compute rule-based gate score for one signal."""
    reasons: list[str] = []
    score = 0

    if signal.event_type in AUTO_PASS_TYPES:
        return GateScore(
            total=100,
            auto_pass=True,
            market_reaction_confirmed=True,
            reasons=["auto_pass:position_protection"],
        )

    if signal.scope == "position_holding" and signal.event_type in POSITION_HIGH_PRIORITY_TYPES:
        return GateScore(
            total=95,
            auto_pass=True,
            market_reaction_confirmed=False,
            reasons=["auto_pass:position_holding_priority"],
        )

    market_ok, market_reasons = has_market_reaction(signal)

    base_by_type: dict[str, int] = {
        "DISCLOSURE_POSITIVE": 62,
        "DISCLOSURE_NEGATIVE": 58,
        "DISCLOSURE_RISK": 75,
        "NEWS_MATERIAL": 35,
        "PRICE_VOLUME_ANOMALY": 68,
        "SUPPLY_DEMAND_SHIFT": 52,
    }
    score = base_by_type.get(signal.event_type, 40)
    reasons.append(f"base:{signal.event_type}:{score}")

    if signal.scope == "position_holding":
        score += 15
        reasons.append("bonus:position_holding:+15")

    if signal.importance_hint == "CRITICAL":
        score += 20
        reasons.append("bonus:critical_hint:+20")
    elif signal.importance_hint == "HIGH":
        score += 10
        reasons.append("bonus:high_hint:+10")

    if market_ok:
        score += 25
        reasons.extend(market_reasons)
        reasons.append("bonus:market_reaction:+25")

    if signal.event_type == "NEWS_MATERIAL":
        if _news_has_material_keyword(signal):
            score += 20
            reasons.append("bonus:news_material_keyword:+20")
        else:
            score -= 25
            reasons.append("penalty:generic_news:-25")
        if signal.scope == "eligible_candidate" and not market_ok and not _news_has_material_keyword(signal):
            score -= 30
            reasons.append("penalty:eligible_news_no_reaction:-30")

    if signal.event_type.startswith("DISCLOSURE") and signal.scope == "eligible_candidate":
        if not market_ok and signal.event_type != "DISCLOSURE_RISK":
            score -= 15
            reasons.append("penalty:disclosure_no_market_reaction:-15")

    if signal.event_type == "PRICE_VOLUME_ANOMALY":
        m = _market_metrics(signal)
        change = m.get("change_rate_pct")
        tv_ratio = m.get("tv_ratio_20d")
        if change is None and tv_ratio is None:
            score -= 20
            reasons.append("penalty:price_anomaly_no_metrics:-20")

    score = max(0, min(100, score))
    auto_pass = score >= 90 and signal.scope == "position_holding"

    return GateScore(
        total=score,
        auto_pass=auto_pass,
        market_reaction_confirmed=market_ok,
        reasons=reasons,
    )
