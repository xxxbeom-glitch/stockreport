"""MVP 4 — 신규 후보 스캔·점수·티어 분류."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

from agents.kr_intraday_slack.entry_price import build_entry_range_fallback
from .candidate_universe import (
    EXCLUDED_LARGE_CAPS,
    candidate_pool_stats,
    list_candidate_entries,
)
from .weekly_metrics import fetch_ohlcv_history

logger = logging.getLogger("weekly_watchlist.candidate_scanner")

DISTANCE_SLACK_OK_PCT = 8.0
DISTANCE_SLACK_RED_MAX_PCT = 12.0

SLACK_MAX_GREEN = 3
SLACK_MAX_YELLOW = 5
SLACK_MAX_RED = 1

DEFAULT_SCAN_LIMIT = 60
DEFAULT_OHLCV_TIMEOUT_SEC = 20.0

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
    pool_total: int = 0
    pool_scan_target: int = 0
    scan_limit: int = DEFAULT_SCAN_LIMIT
    scanned: int = 0
    skipped: int = 0
    excluded_watchlist: int = 0
    excluded_preferred: int = 0
    excluded_low_tv: int = 0
    missing_ohlcv: int = 0
    timeout_ohlcv: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    green: list[dict[str, Any]] = field(default_factory=list)
    yellow: list[dict[str, Any]] = field(default_factory=list)
    red: list[dict[str, Any]] = field(default_factory=list)
    slack_green: list[dict[str, Any]] = field(default_factory=list)
    slack_yellow: list[dict[str, Any]] = field(default_factory=list)
    slack_red: list[dict[str, Any]] = field(default_factory=list)
    slack_red_overflow: int = 0
    excluded_large_caps: int = 0
    candidate_days: int = 5
    daily_scan_path: str | None = None
    all_scored: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


ProgressCallback = Callable[[str], None]


def format_scan_progress_line(
    index: int, total: int, name: str, ticker: str
) -> str:
    return f"[CANDIDATES] scanning {index}/{total} {name}({ticker})"


def format_scan_skip_line(
    name: str, ticker: str, *, reason: str = "missing/timeout"
) -> str:
    return f"[CANDIDATES] skip {reason}: {name}({ticker})"


def format_candidate_scan_summary_line(scan: CandidateScanResult) -> str:
    return (
        f"[CANDIDATES] scanned={scan.scanned} skipped={scan.skipped} "
        f"json={len(scan.candidates)} "
        f"slack=🟢{len(scan.slack_green)} 🟡{len(scan.slack_yellow)} "
        f"🔴{len(scan.slack_red)}"
    )


def _fetch_ohlcv_with_timeout(
    ticker: str,
    *,
    symbol: str,
    timeout_sec: float = DEFAULT_OHLCV_TIMEOUT_SEC,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            fetch_ohlcv_history,
            ticker,
            symbol=symbol,
        )
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeout as exc:
            raise TimeoutError(f"OHLCV timeout {timeout_sec}s") from exc


def _record_skip(
    result: CandidateScanResult,
    *,
    name: str,
    ticker: str,
    reason: str,
    on_line: ProgressCallback | None,
) -> None:
    result.skipped += 1
    if reason == "timeout":
        result.timeout_ohlcv += 1
    else:
        result.missing_ohlcv += 1
    if on_line:
        on_line(format_scan_skip_line(name, ticker, reason=reason))


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


def is_excluded_large_cap(ticker: str, *, include_large_caps: bool = False) -> bool:
    if include_large_caps:
        return False
    return str(ticker).zfill(6) in EXCLUDED_LARGE_CAPS


def watch_zone_mid(row: dict[str, Any]) -> float:
    try:
        lo = int(row.get("entry_low") or 0)
        hi = int(row.get("entry_high") or 0)
    except (TypeError, ValueError):
        return 0.0
    if lo > 0 and hi > 0:
        return (lo + hi) / 2.0
    return 0.0


def compute_distance_pct(row: dict[str, Any]) -> float | None:
    """현재가 vs 볼 구간 중간값 이격률 (%)."""
    current = int(row.get("current_price") or 0)
    mid = watch_zone_mid(row)
    if current <= 0 or mid <= 0:
        return None
    return abs(current - mid) / mid * 100.0


def distance_band(distance_pct: float | None) -> str:
    """
    ok — Slack 🟢/🟡/🔴 점수 티어 그대로 가능
    red_only — Slack에서는 🔴만 (8~12%)
    exclude — Slack 제외, JSON만 (>12% 또는 구간 없음)
    """
    if distance_pct is None:
        return "exclude"
    if distance_pct <= DISTANCE_SLACK_OK_PCT:
        return "ok"
    if distance_pct <= DISTANCE_SLACK_RED_MAX_PCT:
        return "red_only"
    return "exclude"


def enrich_distance_fields(row: dict[str, Any]) -> dict[str, Any]:
    mid = watch_zone_mid(row)
    pct = compute_distance_pct(row)
    band = distance_band(pct)
    row["watch_zone_mid"] = int(mid) if mid > 0 else None
    row["distance_pct"] = round(pct, 2) if pct is not None else None
    row["distance_band"] = band
    row["slack_eligible"] = band != "exclude"
    return row


def effective_slack_tier(row: dict[str, Any]) -> str | None:
    """Slack 섹션용 티어 (None이면 Slack 미표시)."""
    if row.get("excluded_large_cap"):
        return None
    base = str(row.get("tier") or "")
    if base == "exclude":
        return None
    band = str(row.get("distance_band") or "exclude")
    if band == "exclude":
        return None
    if band == "red_only":
        return "red"
    return base


def partition_slack_display(
    scored: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    """🟢≤3 · 🟡≤5 · 🔴≤1, 나머지 red는 overflow."""
    greens: list[dict[str, Any]] = []
    yellows: list[dict[str, Any]] = []
    reds: list[dict[str, Any]] = []

    ordered = sorted(
        scored,
        key=lambda r: (-int(r.get("score") or 0), str(r.get("name") or "")),
    )
    for row in ordered:
        tier = effective_slack_tier(row)
        if tier == "green":
            greens.append(row)
        elif tier == "yellow":
            yellows.append(row)
        elif tier == "red":
            reds.append(row)

    slack_green = greens[:SLACK_MAX_GREEN]
    slack_yellow = yellows[:SLACK_MAX_YELLOW]
    slack_red = reds[:SLACK_MAX_RED]
    overflow = max(0, len(reds) - SLACK_MAX_RED)
    return slack_green, slack_yellow, slack_red, overflow


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
    enrich_distance_fields(row)
    row["ai_reason"] = build_candidate_reason(row)
    row["ai_cancel_condition"] = build_candidate_caution(row)
    return row


def build_candidate_reason(row: dict[str, Any], *, slack_pass: bool = False) -> str:
    """쉬운 문장 1~2개 (금지어 없음)."""
    if slack_pass or row.get("slack_pass_short"):
        return "가격이 볼 구간과 너무 멀어 오늘은 패스합니다."
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


def build_candidate_caution(row: dict[str, Any], *, slack_pass: bool = False) -> str:
    if slack_pass or row.get("slack_pass_short"):
        return "무리해서 따라가지 않는 편이 좋습니다."
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
    scan_limit: int = DEFAULT_SCAN_LIMIT,
    candidate_days: int = 5,
    ohlcv_timeout_sec: float = DEFAULT_OHLCV_TIMEOUT_SEC,
    include_large_caps: bool = False,
    on_progress: ProgressCallback | None = None,
    save_daily_scan_file: bool = True,
) -> CandidateScanResult:
    """
    watchlist 제외 유니버스 스캔 → 상위 후보·티어.
    scan_limit(기본 60): 섹터 우선순위 상위 N종목만 pykrx 조회.
    candidate_days: daily_scan 누적 일수(기본 5) → trend_score·Slack 티어.
    news_by_ticker 미지정 시 data/news/stock_news_{date}.json 시도.
    """
    from .candidate_daily_scan import (
        apply_trend_to_candidates,
        load_recent_candidate_scans,
        partition_slack_by_trend,
        row_to_daily_record,
        save_daily_scan,
    )
    date_key = as_of_date.replace("-", "")[:8]
    if len(date_key) == 8:
        as_of_iso = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:8]}"
    else:
        as_of_iso = as_of_date

    result = CandidateScanResult(as_of_date=as_of_iso)
    pool = candidate_pool_stats(include_large_caps=include_large_caps)
    result.pool_total = pool["pool_total"]
    result.pool_scan_target = pool["pool_scan_target"]
    result.excluded_watchlist = pool["excluded_watchlist"]
    result.excluded_large_caps = pool["excluded_large_caps"]
    result.excluded_preferred = pool["excluded_preferred"]
    limit = scan_limit if scan_limit and scan_limit > 0 else pool["pool_scan_target"]
    result.scan_limit = limit
    result.candidate_days = max(1, int(candidate_days))

    news_map = news_by_ticker if news_by_ticker is not None else _load_news_by_ticker(as_of_iso)

    entries = list_candidate_entries(
        exclude_watchlist=True,
        exclude_large_caps=not include_large_caps,
        exclude_preferred=True,
        scan_limit=limit,
    )
    total = len(entries)
    scored: list[dict[str, Any]] = []
    all_scored: list[dict[str, Any]] = []

    for idx, entry in enumerate(entries, start=1):
        result.scanned += 1
        ticker = str(entry["ticker"]).zfill(6)
        name = str(entry.get("name") or ticker)
        if on_progress:
            on_progress(format_scan_progress_line(idx, total, name, ticker))

        try:
            rows, _meta = _fetch_ohlcv_with_timeout(
                ticker,
                symbol=name,
                timeout_sec=ohlcv_timeout_sec,
            )
        except TimeoutError:
            logger.warning("[%s] OHLCV timeout (%.0fs)", ticker, ohlcv_timeout_sec)
            _record_skip(
                result,
                name=name,
                ticker=ticker,
                reason="timeout",
                on_line=on_progress,
            )
            continue
        except Exception as exc:
            logger.warning("[%s] OHLCV 실패: %s", ticker, exc)
            _record_skip(
                result,
                name=name,
                ticker=ticker,
                reason="missing/timeout",
                on_line=on_progress,
            )
            continue

        if not rows:
            _record_skip(
                result,
                name=name,
                ticker=ticker,
                reason="missing/timeout",
                on_line=on_progress,
            )
            continue

        metrics = _metrics_from_ohlcv(rows)
        if not metrics:
            _record_skip(
                result,
                name=name,
                ticker=ticker,
                reason="missing/timeout",
                on_line=on_progress,
            )
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
        all_scored.append(row)
        if row["tier"] != "exclude":
            scored.append(row)

    if scored:
        from .candidate_agents import build_sector_context, enrich_candidate_with_votes

        sector_ctx = build_sector_context(scored)
        voted: list[dict[str, Any]] = []
        for row in scored:
            ticker = str(row.get("ticker", "")).zfill(6)
            news_ctx = news_map.get(ticker)
            metrics = {
                k: row[k]
                for k in (
                    "return_5d_pct",
                    "tv_increase",
                    "near_high",
                    "latest_trading_value",
                    "current_price",
                )
                if k in row
            }
            voted.append(
                enrich_candidate_with_votes(
                    row,
                    metrics,
                    news_context=news_ctx,
                    sector_context=sector_ctx,
                )
            )
        scored = voted
        voted_by_ticker = {str(r["ticker"]).zfill(6): r for r in scored}
        merged_all: list[dict[str, Any]] = []
        for row in all_scored:
            t = str(row["ticker"]).zfill(6)
            merged_all.append(voted_by_ticker.get(t, row))
        all_scored = merged_all

    result.all_scored = all_scored

    if save_daily_scan_file and all_scored:
        daily_records = [row_to_daily_record(r, as_of_iso) for r in all_scored]
        daily_path = save_daily_scan(as_of_iso, daily_records)
        result.daily_scan_path = str(daily_path)

    history = load_recent_candidate_scans(
        days=result.candidate_days,
        end_date=as_of_iso,
    )

    if scored:
        scored = apply_trend_to_candidates(
            scored,
            history,
            today_date=as_of_iso,
            window_days=result.candidate_days,
        )

    scored.sort(
        key=lambda r: (
            -int(r.get("final_candidate_score") or r.get("score") or 0),
            str(r.get("name") or ""),
        )
    )
    result.candidates = scored[:max_candidates]

    for row in result.candidates:
        tier = row.get("slack_tier") or row.get("tier")
        if tier == "green":
            result.green.append(row)
        elif tier == "yellow":
            result.yellow.append(row)
        elif tier == "red":
            result.red.append(row)

    sg, sy, sr, overflow = partition_slack_by_trend(scored)
    result.slack_green = sg
    result.slack_yellow = sy
    result.slack_red = sr
    result.slack_red_overflow = overflow

    return result


def candidate_rows_for_slack(
    scan: CandidateScanResult,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Slack 표시용 — slack_green/yellow/red (개수 상한 적용됨)."""
    send: list[dict[str, Any]] = []
    for row in scan.slack_green:
        send.append({**row, "ai_decision": "진입 검토", "status": "진입 검토"})
    for row in scan.slack_yellow:
        send.append({**row, "ai_decision": "눌림 확인", "status": "눌림 확인"})
    pass_rows: list[dict[str, Any]] = []
    for row in scan.slack_red:
        pass_rows.append(
            {
                **row,
                "ai_send_slack": False,
                "slack_pass_short": True,
                "ai_reason": build_candidate_reason(row, slack_pass=True),
                "ai_cancel_condition": build_candidate_caution(row, slack_pass=True),
            }
        )
    return send, pass_rows


def format_candidate_scan_log_lines(scan: CandidateScanResult) -> list[str]:
    """CLI·테스트용 [CANDIDATES] 풀·제외 요약 + 실행 요약."""
    lines = [
        f"[CANDIDATES] pool_total={scan.pool_total} scan_target={scan.pool_scan_target}",
        f"[CANDIDATES] scan_limit={scan.scan_limit}",
        f"[CANDIDATES] excluded_watchlist={scan.excluded_watchlist}",
        f"[CANDIDATES] excluded_large_caps={scan.excluded_large_caps}",
    ]
    if scan.excluded_preferred:
        lines.append(f"[CANDIDATES] excluded_preferred={scan.excluded_preferred}")
    if scan.skipped:
        lines.append(f"[CANDIDATES] missing_ohlcv={scan.missing_ohlcv}")
        if scan.timeout_ohlcv:
            lines.append(f"[CANDIDATES] timeout_ohlcv={scan.timeout_ohlcv}")
    if scan.daily_scan_path:
        lines.append(f"[CANDIDATES] daily_scan={scan.daily_scan_path}")
    lines.append(f"[CANDIDATES] trend_days={scan.candidate_days}")
    lines.append(format_candidate_scan_summary_line(scan))
    if scan.slack_red_overflow:
        lines.append(f"[CANDIDATES] slack_red_overflow=+{scan.slack_red_overflow}")
    return lines


def scan_summary_clock(as_of_date: str) -> str:
    return _as_of_clock(as_of_date)
