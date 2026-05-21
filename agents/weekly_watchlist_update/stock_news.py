"""MVP 3-1 — 관심종목 네이버 뉴스·DART 공시 수집."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from data.dart_client import (
    DART_IMPORTANT_KEYWORDS,
    fetch_important_disclosure_items,
    is_dart_configured,
)
from data.kr_watchlist import iter_watchlist_entries
from data.naver_news_client import is_naver_news_configured

from .news_collect import collect_naver_news_for_stock

logger = logging.getLogger("weekly_watchlist.news")

ROOT = Path(__file__).resolve().parents[2]
NEWS_DIR = ROOT / "data" / "news"

NEWS_DAYS = 30
DART_DAYS = 30


def _kst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def _watchlist_rows(metrics: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if metrics:
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in metrics:
            ticker = str(row.get("ticker", "")).strip().zfill(6)
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            rows.append(
                {
                    "ticker": ticker,
                    "symbol": str(row.get("symbol") or row.get("name") or ticker),
                    "sector": str(row.get("sector") or row.get("sector_name") or ""),
                }
            )
        return rows

    out: list[dict[str, str]] = []
    for entry in iter_watchlist_entries():
        ticker = str(entry.get("ticker", "")).strip().zfill(6)
        if not ticker:
            continue
        out.append(
            {
                "ticker": ticker,
                "symbol": str(entry.get("name", "")),
                "sector": str(entry.get("sector_name", "")),
            }
        )
    return out


def collect_stock_news_payload(
    *,
    as_of_date: str,
    metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """25종목 뉴스·공시 수집 (키 없으면 해당 소스만 skip)."""
    naver_ok = is_naver_news_configured()
    dart_ok = is_dart_configured()
    warnings: list[str] = []

    if not naver_ok:
        warnings.append("naver_news_skipped: NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 없음")
    if not dart_ok:
        warnings.append("dart_disclosures_skipped: DART_API_KEY 없음")

    stocks_out: list[dict[str, Any]] = []
    for item in _watchlist_rows(metrics):
        ticker = item["ticker"]
        symbol = item["symbol"]
        stock_row: dict[str, Any] = {
            "ticker": ticker,
            "symbol": symbol,
            "sector": item["sector"],
            "naver_news": [],
            "dart_disclosures": [],
            "news_count": 0,
            "dart_count": 0,
            "errors": [],
        }

        if naver_ok:
            try:
                stock_row["naver_news"] = collect_naver_news_for_stock(
                    symbol,
                    item["sector"],
                    ticker=ticker,
                    max_age_days=NEWS_DAYS,
                )
            except Exception as exc:
                logger.warning(
                    "[%s %s] 네이버 뉴스 수집 실패: %s",
                    symbol,
                    ticker,
                    type(exc).__name__,
                )
                stock_row["errors"].append(f"naver:{type(exc).__name__}")

        if dart_ok:
            try:
                stock_row["dart_disclosures"] = fetch_important_disclosure_items(
                    ticker,
                    days=DART_DAYS,
                )
            except Exception as exc:
                logger.warning(
                    "[%s %s] DART 공시 수집 실패: %s",
                    symbol,
                    ticker,
                    type(exc).__name__,
                )
                stock_row["errors"].append(f"dart:{type(exc).__name__}")

        stock_row["news_count"] = len(stock_row["naver_news"])
        stock_row["dart_count"] = len(stock_row["dart_disclosures"])
        logger.info(
            "[%s %s] news_count=%d dart_count=%d",
            symbol,
            ticker,
            stock_row["news_count"],
            stock_row["dart_count"],
        )
        stocks_out.append(stock_row)

    return {
        "version": "weekly_watchlist_news_v2",
        "as_of_date": as_of_date,
        "generated_at": _kst_now().isoformat(),
        "sources": {
            "naver_news": {
                "configured": naver_ok,
                "skipped": not naver_ok,
            },
            "dart_disclosures": {
                "configured": dart_ok,
                "skipped": not dart_ok,
            },
        },
        "params": {
            "news_max_age_days": NEWS_DAYS,
            "dart_days": DART_DAYS,
            "naver_display": 10,
            "naver_top_n": 3,
            "news_quality_scoring": "v3_1_5",
            "dart_top_n": 3,
            "dart_important_keywords": list(DART_IMPORTANT_KEYWORDS),
        },
        "stocks": stocks_out,
        "warnings": warnings,
    }


def write_stock_news_file(
    payload: dict[str, Any],
    *,
    as_of_date: str | None = None,
) -> Path:
    """data/news/stock_news_YYYY-MM-DD.json 저장."""
    date_key = as_of_date or str(payload.get("as_of_date", ""))
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    path = NEWS_DIR / f"stock_news_{date_key}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("stock_news 저장: %s (%d종목)", path.name, len(payload.get("stocks") or []))
    return path


def collect_and_save_stock_news(
    as_of_date: str,
    *,
    metrics: list[dict[str, Any]] | None = None,
) -> Path:
    """수집 + JSON 저장. 예외는 호출부에서 처리."""
    payload = collect_stock_news_payload(as_of_date=as_of_date, metrics=metrics)
    return write_stock_news_file(payload, as_of_date=as_of_date)
