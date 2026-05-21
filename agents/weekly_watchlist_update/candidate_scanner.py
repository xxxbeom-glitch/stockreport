"""MVP 4 — 신규 후보 스캔·점수·티어 분류."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agents.kr_intraday_slack.entry_price import build_entry_range_fallback
from data.kr_watchlist import watchlist_ticker_set

from .candidate_universe import iter_candidate_entries
from .weekly_metrics import fetch_ohlcv_history

logger = logging.getLogger("weekly_watchlist.candidate_scanner")

MAX_CANDIDATES = 10
MIN_SCORE_SLACK = 35
TIER_GREEN_MIN = 70
TIER_YELLOW_MIN = 50
TIER_RED_MIN = 35

MIN_LATEST_TRADING_VALUE = 500_000_000  # 5억 원 미만 제외
OVERHEAT_5D_PCT = 15.0
NEAR_HIGH_RATIO = 0.97
TV_INCREASE_RATIO = 1.10

SCORE_RETURN_5D = 20
SCORE_TV_INCREASE = 25
SCORE_NEAR_HIGH = 20
SCORE_HAS_NEWS = 15
SCORE_HAS_DART = 15
SCORE_OVERHEAT_PENALTY = -15


@dataclass
class CandidateScanResult:
    as_of_date: str
    scanned: int = 0
    excluded_watchlist: int = 0
    excluded_low_tv: int = 0
    excluded_no_data: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    green: list[dict[str, Any]] = field(default_factory=list)
    yellow: list[dict[str, Any]] = field(default_factory=list)
    red: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _as_of_clock(as_of_date: str) -> str:
    """Slack 기준 시각 — 주간 배치는 장 마감 기준."""
    if " " in as_of_date:
        return as_of_date.split()[-1]
    return "15:30"


def _load_news_by_ticker(as_of_date: str) -> dict[str, dict[str, Any]]:
    try:
        from .news_context import load_stock_news

        payload = load_stock_news(as_of_date)
    except Exception:
        return {}
    stocks = payload.get("stocks") if isinstance(payload, dict) else None
    if not isinstance(stocks, dict):
        return {}
    return {str(k).zfill(6): v for k, v in stocks.items() if isinstance(v, dict)}


def _news_dart_flags(
    ticker: str, news_by_ticker: dict[str, dict[str, Any]]
) -> tuple[bool, bool]:
    entry = news_by_ticker.get(ticker.zfill(6)) or {}
    has_news = bool(entry.get("news"))
    has_dart = bool(entry.get("dart_disclosures") or entry.get("disclosures"))
    return has_news, has_dart


def _metrics_from_ohlcv(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(rows) < 5:
        return None
    tail = rows[-5:]
    closes = [float(r["close"]) for r in tail if float(r.get("close") or 0) > 0]
    if len(closes) < 2:
        return None
    tvs = [float(r.get("trading_value") or 0) for r in tail]
    highs = [float(r.get("high") or r.get("close") or 0) for r in rows[-20:]]
    current = closes[-1]
    start = closes[0]
    return_5d = ((current / start) - 1.0) * 100.0 if start > 0 else 0.0
    recent_tv = sum(tvs[-2:]) / max(1, min(2, len(tvs[-2:])))
    prior_tv = sum(tvs[:-2]) / max(1, len(tvs[:-2]) or 1)
    tv_increase = prior_tv > 0 and recent_tv >= prior_tv * TV_INCREASE_RATIO
    peak = max(highs) if highs else current
    near_high = peak > 0 and (current / peak) >= NEAR_HIGH_RATIO
    latest_tv = tvs[-1] if tvs else 0.0
    return {
        "current_price": int(current),
        "return_5d_pct": round(return_5d, 2),
        "tv_increase": tv_increase,
        "near_high": near_high,
        "latest_trading_value": latest_tv,
        "day_high": int(max(float(r.get("high") or 0) for r in tail)),
        "day_low": int(min(float(r.get("low") or current) for r in tail)),
        "prev_close": int(closes[-2]) if len(closes) >= 2 else int(current),
    }


def score_candidate(
    base: dict[str, Any],
    metrics: dict[str, Any],
    *,
    has_news: bool = False,
    has_dart: bool = False,
) -> dict[str, Any]:
    """규칙 점수 + 티어."""
    breakdown: dict[str, int] = {}
    score = 0

    ret = float(metrics.get("return_5d_pct") or 0)
    if ret > 0:
        breakdown["return_5d"] = SCORE_RETURN_5D
        score += SCORE_RETURN_5D

    if metrics.get("tv_increase"):
        breakdown["tv_increase"] = SCORE_TV_INCREASE
        score += SCORE_TV_INCREASE

    if metrics.get("near_high"):
        breakdown["near_high"] = SCORE_NEAR_HIGH
        score += SCORE_NEAR_HIGH

    if has_news:
        breakdown["news"] = SCORE_HAS_NEWS
        score += SCORE_HAS_NEWS

    if has_dart:
        breakdown["dart"] = SCORE_HAS_DART
        score += SCORE_HAS_DART

    if ret >= OVERHEAT_5D_PCT:
        breakdown["overheat_penalty"] = SCORE_OVERHEAT_PENALTY
        score += SCORE_OVERHEAT_PENALTY

    if score >= TIER_GREEN_MIN:
        tier = "green"
    elif score >= TIER_YELLOW_MIN:
        tier = "yellow"
    elif score >= TIER_RED_MIN:
        tier = "red"
    else:
        tier = "exclude"

    row = {
        **base,
        **metrics,
        "score": score,
        "score_breakdown": breakdown,
        "tier": tier,
        "has_news": has_news,
        "has_dart": has_dart,
        "current_price_fmt": f"{int(metrics['current_price']):,}원",
    }
    entry_range, lo, hi, src = build_entry_range_fallback(row)
    row["entry_range"] = entry_range
    row["entry_low"] = lo
    row["entry_high"] = hi
    row["entry_range_source"] = src
    row["ai_reason"] = build_candidate_reason(row)
    row["ai_cancel_condition"] = build_candidate_caution(row)
    return row


def build_candidate_reason(row: dict[str, Any]) -> str:
    """쉬운 문장 1~2개 (금지어 없음)."""
    parts: list[str] = []
    ret = float(row.get("return_5d_pct") or 0)
    if ret > 0 and row.get("tv_increase"):
        parts.append("최근 가격 흐름이 좋고 거래도 평소보다 늘었습니다.")
    elif ret > 0:
        parts.append("최근 가격 흐름이 나쁘지 않습니다.")
    elif row.get("tv_increase"):
        parts.append("거래가 평소보다 늘면서 관심이 붙는 모습입니다.")

    if row.get("has_news") or row.get("has_dart"):
        if row.get("has_news") and row.get("has_dart"):
            parts.append("관련 뉴스와 공시가 있어 오늘 계속 지켜볼 만합니다.")
        elif row.get("has_news"):
            parts.append("관련 뉴스가 있어 오늘 계속 지켜볼 만합니다.")
        else:
            parts.append("관련 공시가 있어 흐름을 조금 더 볼 만합니다.")

    sector = str(row.get("sector_name") or "").strip()
    if len(parts) < 2 and sector:
        parts.append(f"{sector} 쪽에서 새로 짚어볼 만한 종목입니다.")
    if not parts:
        parts.append("오늘 장에서 다시 흐름을 확인할 만합니다.")
    if float(row.get("return_5d_pct") or 0) >= OVERHEAT_5D_PCT and len(parts) < 2:
        parts.append("다만 단기간에 많이 오른 편이라 무리하지 않는 게 좋습니다.")
    return " ".join(parts[:2])


def build_candidate_caution(row: dict[str, Any]) -> str:
    tier = str(row.get("tier") or "")
    ret = float(row.get("return_5d_pct") or 0)
    if tier == "red" or ret >= OVERHEAT_5D_PCT:
        return "관심은 둘 만하지만 오늘은 무리하지 않는 편이 낫습니다."
    if tier == "yellow":
        return "흐름은 좋지만 지금 가격은 조금 높은 편입니다. 바로 따라가기보다는 살짝 내려오는지 보는 게 좋습니다."
    return "바로 따라가기보다는 살짝 눌리는지 보는 게 좋습니다."


def run_candidate_scan(
    *,
    as_of_date: str,
    news_by_ticker: dict[str, dict[str, Any]] | None = None,
    max_candidates: int = MAX_CANDIDATES,
) -> CandidateScanResult:
    """
    watchlist 제외 유니버스 스캔 → 상위 후보·티어.
    news_by_ticker 미지정 시 data/news/stock_news_{date}.json 시도.
    """
    date_key = as_of_date.replace("-", "")[:8]
    if len(date_key) == 8:
        as_of_iso = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:8]}"
    else:
        as_of_iso = as_of_date

    result = CandidateScanResult(as_of_date=as_of_iso)
    watchlist = watchlist_ticker_set()
    news_map = news_by_ticker if news_by_ticker is not None else _load_news_by_ticker(as_of_iso)

    scored: list[dict[str, Any]] = []
    for entry in iter_candidate_entries(exclude_watchlist=True):
        result.scanned += 1
        ticker = str(entry["ticker"]).zfill(6)
        if ticker in watchlist:
            result.excluded_watchlist += 1
            continue

        try:
            rows, _meta = fetch_ohlcv_history(
                ticker,
                symbol=str(entry.get("name") or ticker),
            )
        except Exception as exc:
            logger.warning("[%s] OHLCV 실패: %s", ticker, exc)
            result.excluded_no_data += 1
            continue

        metrics = _metrics_from_ohlcv(rows)
        if not metrics:
            result.excluded_no_data += 1
            continue

        if metrics["latest_trading_value"] < MIN_LATEST_TRADING_VALUE:
            result.excluded_low_tv += 1
            continue

        has_news, has_dart = _news_dart_flags(ticker, news_map)
        row = score_candidate(
            dict(entry),
            metrics,
            has_news=has_news,
            has_dart=has_dart,
        )
        if row["tier"] != "exclude":
            scored.append(row)

    scored.sort(key=lambda r: (-int(r.get("score") or 0), str(r.get("name") or "")))
    result.candidates = scored[:max_candidates]

    for row in result.candidates:
        tier = row.get("tier")
        if tier == "green":
            result.green.append(row)
        elif tier == "yellow":
            result.yellow.append(row)
        elif tier == "red":
            result.red.append(row)

    return result


def candidate_rows_for_slack(scan: CandidateScanResult) -> tuple[list[dict], list[dict]]:
    """compose_new_candidate_scan_message용 — green/yellow send, red pass."""
    send: list[dict[str, Any]] = []
    for row in scan.green:
        send.append({**row, "ai_decision": "진입 검토", "status": "진입 검토"})
    for row in scan.yellow:
        send.append({**row, "ai_decision": "눌림 확인", "status": "눌림 확인"})
    pass_rows = [{**row, "ai_send_slack": False} for row in scan.red]
    return send, pass_rows


def scan_summary_clock(as_of_date: str) -> str:
    return _as_of_clock(as_of_date)
