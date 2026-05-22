# -*- coding: utf-8 -*-
"""네이버 금융 coinfo 기업개요 (사업 설명) 수집 — mock_trading 전용."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = ROOT / "data" / "mock_trading" / "naver_business_profile_cache.json"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _parse_coinfo_paragraphs(html: str) -> str:
    """기업개요 영역 <p> 텍스트 결합."""
    block = html
    m = re.search(
        r'<div[^>]+id="summary_info"[^>]*>([\s\S]*?)</div>\s*</div>',
        html,
        re.IGNORECASE,
    )
    if m:
        block = m.group(1)
    paragraphs = re.findall(r"<p[^>]*>([^<]+)</p>", block, re.IGNORECASE)
    cleaned = [re.sub(r"\s+", " ", p).strip() for p in paragraphs if p.strip()]
    return " ".join(cleaned).strip()


def fetch_naver_business_summary(ticker: str, *, timeout: float = 12.0) -> str | None:
    code = str(ticker).strip().zfill(6)
    url = f"https://finance.naver.com/item/coinfo.naver?code={code}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.debug("naver coinfo %s 실패: %s", code, type(exc).__name__)
        return None

    for enc in ("euc-kr", "utf-8", "cp949"):
        try:
            html = raw.decode(enc)
            break
        except UnicodeDecodeError:
            html = ""
    if not html:
        return None

    text = _parse_coinfo_paragraphs(html)
    return text or None


def load_profile_cache(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_CACHE_PATH
    if not p.is_file():
        return {"version": 1, "profiles": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "profiles": {}}
    if not isinstance(data, dict):
        return {"version": 1, "profiles": {}}
    data.setdefault("profiles", {})
    return data


def save_profile_cache(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or DEFAULT_CACHE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_or_fetch_profiles(
    tickers: list[str],
    *,
    cache_path: Path | None = None,
    delay_sec: float = 0.12,
    refresh: bool = False,
    max_fetch: int = 0,
) -> dict[str, str]:
    """
    티커별 사업개요 텍스트. 캐시 우선, 없으면 네이버 조회.
    max_fetch>0 이면 신규 HTTP 조회 상한.
    """
    cache = load_profile_cache(cache_path)
    profiles: dict[str, Any] = cache.get("profiles") or {}
    out: dict[str, str] = {}
    fetched = 0

    for raw in tickers:
        code = str(raw).strip().zfill(6)
        if not refresh and code in profiles:
            entry = profiles[code]
            if isinstance(entry, dict) and entry.get("summary"):
                out[code] = str(entry["summary"])
                continue

        if max_fetch > 0 and fetched >= max_fetch:
            continue

        summary = fetch_naver_business_summary(code)
        fetched += 1
        profiles[code] = {
            "summary": summary or "",
            "source": "naver_coinfo",
            "ok": bool(summary),
        }
        if summary:
            out[code] = summary
        if delay_sec > 0:
            time.sleep(delay_sec)

    cache["profiles"] = profiles
    save_profile_cache(cache, cache_path)
    return out
