"""MVP 4-3 — 일별 후보 스캔 저장·최근 N일 누적 trend_score."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .candidate_scanner import TIER_RED_MIN

logger = logging.getLogger("weekly_watchlist.candidate_daily_scan")

ROOT = Path(__file__).resolve().parents[2]
DAILY_SCAN_DIR = ROOT / "data" / "daily_scan"

TREND_DAYS_DEFAULT = 5
TREND_MULTI_DAY_CANDIDATE = 20
TREND_MULTI_DAY_TV = 20
TREND_MULTI_DAY_RISE = 15
TREND_NEWS_DAYS = 15
TREND_DECLINING_PENALTY = -15
TREND_ONE_DAY_SPIKE = -10

TREND_GOOD_MIN = 25
TODAY_GOOD_MIN = 50


def _normalize_date(date_str: str) -> str:
    key = str(date_str or "").replace("-", "")[:8]
    if len(key) == 8:
        return f"{key[:4]}-{key[4:6]}-{key[6:8]}"
    return str(date_str)


def is_candidate_day_record(record: dict[str, Any]) -> bool:
    """해당 일자에 후보로 인정된 기록인지."""
    tier = str(record.get("tier") or "exclude")
    score = int(record.get("score") or 0)
    return tier != "exclude" or score >= TIER_RED_MIN


def row_to_daily_record(row: dict[str, Any], date: str) -> dict[str, Any]:
    """data/daily_scan/YYYY-MM-DD.json 레코드 1건."""
    return {
        "date": _normalize_date(date),
        "ticker": str(row.get("ticker") or "").zfill(6),
        "name": str(row.get("name") or ""),
        "sector": str(row.get("sector_name") or row.get("sector") or ""),
        "current_price": row.get("current_price"),
        "return_5d": row.get("return_5d_pct", row.get("return_5d")),
        "trading_value": row.get("latest_trading_value", row.get("trading_value")),
        "trading_value_change": bool(
            row.get("tv_increase", row.get("trading_value_change"))
        ),
        "near_high": bool(row.get("near_high")),
        "has_news": bool(row.get("has_news")),
        "has_dart": bool(row.get("has_dart")),
        "score": int(row.get("score") or 0),
        "tier": str(row.get("tier") or "exclude"),
        "agent_votes": row.get("agent_votes"),
        "vote_summary": row.get("vote_summary"),
        "final_opinion": row.get("final_opinion"),
    }


def save_daily_scan(
    date: str,
    records: list[dict[str, Any]],
    *,
    scan_dir: Path | None = None,
) -> Path:
    """일별 스캔 JSON 저장. 이후 증분 재조회용 ticker 목록도 함께 보관."""
    out_dir = scan_dir or DAILY_SCAN_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = _normalize_date(date)
    path = out_dir / f"{iso}.json"
    tickers = sorted({str(r.get("ticker") or "").zfill(6) for r in records if r.get("ticker")})
    payload = {
        "version": "daily_scan_v1",
        "date": iso,
        "record_count": len(records),
        "tickers": tickers,
        "records": records,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[CANDIDATES] daily_scan saved %s (%d records)", path, len(records))
    return path


def _parse_daily_file(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("daily_scan 읽기 실패 %s: %s", path.name, exc)
        return []
    records = raw.get("records") if isinstance(raw, dict) else None
    if not isinstance(records, list):
        return []
    out: list[dict[str, Any]] = []
    for rec in records:
        if isinstance(rec, dict) and rec.get("ticker"):
            item = dict(rec)
            item["date"] = _normalize_date(str(item.get("date") or raw.get("date") or path.stem))
            item["ticker"] = str(item["ticker"]).zfill(6)
            out.append(item)
    return out


def load_recent_candidate_scans(
    days: int = TREND_DAYS_DEFAULT,
    *,
    end_date: str | None = None,
    scan_dir: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    최근 N일 daily_scan 파일을 읽어 ticker → 일별 기록 리스트.
    없는 날짜·깨진 파일은 건너뜀.
    """
    base = scan_dir or DAILY_SCAN_DIR
    if not base.is_dir():
        return {}

    end_iso = _normalize_date(end_date or datetime.now().strftime("%Y-%m-%d"))
    try:
        end_dt = datetime.strptime(end_iso, "%Y-%m-%d")
    except ValueError:
        end_dt = datetime.now()

    wanted_dates: set[str] = set()
    for i in range(max(1, days)):
        d = (end_dt - timedelta(days=i)).strftime("%Y-%m-%d")
        wanted_dates.add(d)

    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for iso in sorted(wanted_dates, reverse=True):
        path = base / f"{iso}.json"
        if not path.is_file():
            continue
        for rec in _parse_daily_file(path):
            ticker = str(rec["ticker"]).zfill(6)
            by_ticker.setdefault(ticker, []).append(rec)

    for ticker in by_ticker:
        by_ticker[ticker].sort(key=lambda r: str(r.get("date") or ""))
    return by_ticker


def compute_trend_score(
    history: list[dict[str, Any]],
    *,
    window_days: int = TREND_DAYS_DEFAULT,
) -> dict[str, Any]:
    """최근 N일 기록으로 trend_score·breakdown·메타 계산."""
    if not history:
        return {
            "trend_score": 0,
            "trend_breakdown": {},
            "trend_days_seen": 0,
            "trend_candidate_days": 0,
            "one_day_spike": False,
            "scores_declining": False,
        }

    sorted_hist = sorted(history, key=lambda r: str(r.get("date") or ""))[-window_days:]
    unique_dates = {str(r.get("date") or "") for r in sorted_hist if r.get("date")}
    days_seen = len(unique_dates)

    candidate_days = sum(1 for r in sorted_hist if is_candidate_day_record(r))
    tv_days = sum(
        1
        for r in sorted_hist
        if r.get("trading_value_change") or r.get("tv_increase")
    )
    rise_days = sum(1 for r in sorted_hist if float(r.get("return_5d") or 0) > 0)
    news_days = sum(
        1 for r in sorted_hist if r.get("has_news") or r.get("has_dart")
    )

    breakdown: dict[str, int] = {}
    score = 0

    if candidate_days >= 3:
        breakdown["multi_day_candidate"] = TREND_MULTI_DAY_CANDIDATE
        score += TREND_MULTI_DAY_CANDIDATE
    if tv_days >= 3:
        breakdown["multi_day_tv"] = TREND_MULTI_DAY_TV
        score += TREND_MULTI_DAY_TV
    if rise_days >= 3:
        breakdown["multi_day_rise"] = TREND_MULTI_DAY_RISE
        score += TREND_MULTI_DAY_RISE
    if news_days >= 2:
        breakdown["news_days"] = TREND_NEWS_DAYS
        score += TREND_NEWS_DAYS

    scores = [int(r.get("score") or 0) for r in sorted_hist]
    scores_declining = (
        len(scores) >= 3 and all(scores[i] > scores[i + 1] for i in range(len(scores) - 1))
    )
    if scores_declining:
        breakdown["declining_scores"] = TREND_DECLINING_PENALTY
        score += TREND_DECLINING_PENALTY

    one_day_spike = days_seen <= 1
    if one_day_spike:
        breakdown["one_day_spike"] = TREND_ONE_DAY_SPIKE
        score += TREND_ONE_DAY_SPIKE

    return {
        "trend_score": score,
        "trend_breakdown": breakdown,
        "trend_days_seen": days_seen,
        "trend_candidate_days": candidate_days,
        "one_day_spike": one_day_spike,
        "scores_declining": scores_declining,
    }


def build_trend_candidate_reason(row: dict[str, Any], *, slack_pass: bool = False) -> str:
    """누적 흐름 반영 Slack 이유 문장."""
    if slack_pass or row.get("slack_pass_short"):
        return "가격이 볼 구간과 너무 멀어 오늘은 패스합니다."

    slack_tier = str(row.get("slack_tier") or row.get("tier") or "")
    if row.get("one_day_spike") or slack_tier == "red":
        if row.get("one_day_spike"):
            return "하루만 강하게 움직인 상태라 오늘은 무리하지 않는 편이 좋습니다."
        if str(row.get("distance_band") or "") in ("exclude", "red_only"):
            return "가격이 볼 구간과 너무 멀어 오늘은 무리하지 않는 편이 좋습니다."

    trend = int(row.get("trend_score") or 0)
    if slack_tier == "green" and trend >= TREND_GOOD_MIN:
        return (
            "최근 며칠 동안 거래가 꾸준히 늘고 있고, "
            "오늘도 가격 흐름이 이어지고 있습니다."
        )
    if slack_tier == "yellow":
        return (
            "오늘은 좋아 보이지만 최근 흐름은 아직 짧아 "
            "조금 더 확인이 필요합니다."
        )
    return "오늘 장에서 다시 흐름을 확인할 만합니다."


def assign_slack_tier_from_trend(row: dict[str, Any]) -> tuple[str, bool]:
    """
    today_score + trend_score 기준 Slack 티어.
    Returns (slack_tier, slack_pass_short).
    """
    today_score = int(row.get("today_score") or row.get("score") or 0)
    trend_score = int(row.get("trend_score") or 0)
    band = str(row.get("distance_band") or "exclude")
    dist = row.get("distance_pct")

    if band == "exclude":
        return "red", True
    if row.get("one_day_spike") and trend_score < TREND_GOOD_MIN:
        return "red", True

    today_good = today_score >= TODAY_GOOD_MIN
    trend_good = trend_score >= TREND_GOOD_MIN

    if band == "red_only":
        return "red", True

    if today_good and trend_good:
        return "green", False
    if today_good and not trend_good:
        return "yellow", False
    if trend_good and not today_good:
        return "yellow", False
    if today_score >= TIER_RED_MIN and trend_score >= 0:
        return "yellow", False

    return "red", False


def enrich_row_with_trend(
    row: dict[str, Any],
    history_by_ticker: dict[str, list[dict[str, Any]]],
    *,
    today_date: str,
    window_days: int = TREND_DAYS_DEFAULT,
) -> dict[str, Any]:
    """today_score·trend_score·final_candidate_score·Slack 티어 부여."""
    ticker = str(row.get("ticker") or "").zfill(6)
    today_iso = _normalize_date(today_date)
    today_rec = row_to_daily_record(row, today_iso)

    prior = list(history_by_ticker.get(ticker, []))
    prior = [r for r in prior if _normalize_date(str(r.get("date") or "")) != today_iso]
    history = prior + [today_rec]
    trend_meta = compute_trend_score(history, window_days=window_days)

    out = {**row}
    out["today_score"] = int(row.get("score") or 0)
    out.update(trend_meta)
    out["final_candidate_score"] = out["today_score"] + int(out["trend_score"])

    slack_tier, slack_pass = assign_slack_tier_from_trend(out)
    out["slack_tier"] = slack_tier
    out["slack_pass_short"] = slack_pass
    out["ai_reason"] = build_trend_candidate_reason(out, slack_pass=slack_pass)
    return out


def apply_trend_to_candidates(
    rows: list[dict[str, Any]],
    history_by_ticker: dict[str, list[dict[str, Any]]],
    *,
    today_date: str,
    window_days: int = TREND_DAYS_DEFAULT,
) -> list[dict[str, Any]]:
    enriched = [
        enrich_row_with_trend(
            row,
            history_by_ticker,
            today_date=today_date,
            window_days=window_days,
        )
        for row in rows
    ]
    enriched.sort(
        key=lambda r: (
            -int(r.get("final_candidate_score") or 0),
            str(r.get("name") or ""),
        )
    )
    return enriched


_SLACK_MAX_GREEN = 3
_SLACK_MAX_YELLOW = 5
_SLACK_MAX_RED = 1


def partition_slack_by_trend(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    """final_candidate_score 순 · slack_tier 기준 🟢🟡🔴."""
    greens: list[dict[str, Any]] = []
    yellows: list[dict[str, Any]] = []
    reds: list[dict[str, Any]] = []

    for row in rows:
        tier = str(row.get("slack_tier") or "")
        if tier == "green" and not row.get("slack_pass_short"):
            greens.append(row)
        elif tier == "yellow" and not row.get("slack_pass_short"):
            yellows.append(row)
        elif tier == "red":
            reds.append(row)

    slack_green = greens[:_SLACK_MAX_GREEN]
    slack_yellow = yellows[:_SLACK_MAX_YELLOW]
    slack_red = reds[:_SLACK_MAX_RED]
    overflow = max(0, len(reds) - _SLACK_MAX_RED)
    return slack_green, slack_yellow, slack_red, overflow
