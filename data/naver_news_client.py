"""네이버 검색 뉴스 API (선택 — NAVER_CLIENT_ID / NAVER_CLIENT_SECRET)."""

from __future__ import annotations

import logging
import re
from typing import Any

from data.api_env import getenv

logger = logging.getLogger(__name__)

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
_WARNED_NO_CREDENTIALS = False


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", str(text or "")).strip()


_strip_html = strip_html  # backward compat


def is_naver_news_configured() -> bool:
    return bool(getenv("NAVER_CLIENT_ID") and getenv("NAVER_CLIENT_SECRET"))


def _warn_skip_once() -> None:
    global _WARNED_NO_CREDENTIALS
    if _WARNED_NO_CREDENTIALS:
        return
    _WARNED_NO_CREDENTIALS = True
    logger.warning(
        "NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 없음 — 네이버 뉴스 수집을 건너뜁니다"
    )


def search_raw_news(
    query: str,
    *,
    display: int = 10,
    sort: str = "date",
) -> list[dict[str, Any]]:
    """네이버 뉴스 API 원본 항목 (HTML 미제거). 미설정 시 [] + warning."""
    client_id = getenv("NAVER_CLIENT_ID")
    client_secret = getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        _warn_skip_once()
        return []

    import requests

    q = str(query).strip()
    if not q:
        return []

    try:
        resp = requests.get(
            NAVER_NEWS_URL,
            params={"query": q, "display": max(1, min(display, 100)), "sort": sort},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("네이버 뉴스 API 요청 실패: %s", type(exc).__name__)
        return []

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    return [dict(row) for row in items if isinstance(row, dict)]


def search_stock_news(
    query: str,
    *,
    display: int = 5,
    sort: str = "date",
) -> list[dict[str, Any]]:
    """간단 검색 (HTML 제거). 상세 필터는 news_collect 사용."""
    results: list[dict[str, Any]] = []
    for row in search_raw_news(query, display=display, sort=sort):
        results.append(
            {
                "title": strip_html(str(row.get("title", ""))),
                "link": str(row.get("link", "")).strip(),
                "description": strip_html(str(row.get("description", ""))),
                "pub_date": str(row.get("pubDate", "")).strip(),
                "originallink": str(row.get("originallink", "")).strip(),
                "source": "naver_search_news",
            }
        )
    return results
