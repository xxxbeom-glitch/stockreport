"""MVP 3-1 / 3-1.5 — 네이버 뉴스 수집·필터·관련도·품질 점수 (LLM 미사용)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

from data.naver_news_client import search_raw_news

KST = timezone(timedelta(hours=9))

NEWS_MAX_AGE_DAYS = 30
NEWS_TOP_N = 3
NEWS_DISPLAY = 10
MAX_PER_DOMAIN = 2
TITLE_LEAD_CHARS = 20
SHORT_SYMBOL_MAX_LEN = 3

NEWS_TOPIC_KEYWORDS: tuple[str, ...] = (
    "실적",
    "수주",
    "공시",
    "증설",
    "투자",
    "목표가",
    "리포트",
)

TITLE_THEME_KEYWORDS: tuple[str, ...] = (
    "반도체주",
    "소부장주",
    "테마주",
    "이 시각 시황",
    "브랜드평판",
    "이격도과열",
    "오늘의 IR",
    "주요공시",
    "마감시황",
)

MAX_QUERIES_PER_STOCK = 3

# ticker → 네이버 검색 alias (종목당 쿼리 최대 MAX_QUERIES_PER_STOCK)
STOCK_NEWS_ALIASES: dict[str, list[str]] = {
    "099320": ["세트렉아이", "쎄트렉아이"],
    "010620": ["HD현대미포", "현대미포조선"],
    "023160": ["태광 조선기자재", "태광 피팅", "태광 산업용 밸브"],
    "042370": ["비츠로테크 전력", "비츠로테크 방산"],
    "033500": ["동성화인텍 LNG", "동성화인텍 보냉재"],
    "017960": ["한국카본 LNG", "한국카본 보볉재"],
}

# symbol fallback (ticker 매핑 없을 때)
STOCK_SEARCH_ALIASES: dict[str, list[str]] = {
    "세트렉아이": ["세트렉아이", "쎄트렉아이"],
    "HD현대미포": ["HD현대미포", "현대미포조선"],
    "태광": ["태광 조선기자재", "태광 피팅", "태광 산업용 밸브"],
    "비츠로테크": ["비츠로테크 전력", "비츠로테크 방산"],
    "동성화인텍": ["동성화인텍 LNG", "동성화인텍 보냉재"],
    "한국카본": ["한국카본 LNG", "한국카본 보냉재"],
}

HOMONYM_NOISE_PATTERNS: dict[str, tuple[str, ...]] = {
    "태광": ("태광그룹", "태광그룹주"),
}

HOMONYM_STRONG_HINTS: dict[str, tuple[str, ...]] = {
    "태광": ("조선기자재", "피팅", "밸브", "산업용", "023160"),
}


@dataclass(frozen=True)
class MatchInfo:
    matched: bool
    matched_term: str
    direct_title_match: bool
    title_lead_match: bool
    description_only_match: bool
    theme_article: bool
    multi_stock_roundup: bool
    possible_name_noise: bool


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", str(text or "")).strip()


def normalize_title(title: str) -> str:
    t = strip_html(title).lower()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[^\w가-힣]", "", t)
    return t


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def sector_keyword(sector: str) -> str:
    s = str(sector or "").strip()
    if not s:
        return ""
    if "·" in s:
        return s.split("·")[0].strip()
    if " " in s:
        return s.split()[0].strip()
    return s


def _aliases_for_stock(symbol: str, ticker: str | None = None) -> list[str]:
    code = str(ticker or "").strip().zfill(6)
    if code and code in STOCK_NEWS_ALIASES:
        return list(STOCK_NEWS_ALIASES[code])
    return list(STOCK_SEARCH_ALIASES.get(symbol, [symbol]))


def search_queries_for_symbol(
    symbol: str,
    sector: str,
    *,
    ticker: str | None = None,
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    sym = str(symbol).strip()
    if sym and sym not in seen:
        seen.add(sym)
        out.append(sym)
    for q in _aliases_for_stock(sym, ticker):
        q = str(q).strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= MAX_QUERIES_PER_STOCK:
            return out[:MAX_QUERIES_PER_STOCK]
    sector_kw = sector_keyword(sector)
    if sector_kw and len(out) < MAX_QUERIES_PER_STOCK:
        combined = f"{sym} {sector_kw}".strip()
        if combined not in seen:
            seen.add(combined)
            out.append(combined)
    return out[:MAX_QUERIES_PER_STOCK]


def match_terms_for_symbol(symbol: str, *, ticker: str | None = None) -> list[str]:
    terms = _aliases_for_stock(symbol, ticker)
    if symbol not in terms:
        terms.insert(0, symbol)
    terms.sort(key=len, reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        c = _compact(t)
        if c and c not in seen:
            seen.add(c)
            out.append(t)
    return out


def parse_pub_date(pub_date: str) -> datetime | None:
    raw = str(pub_date or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except Exception:
        return None


def _kst_now() -> datetime:
    return datetime.now(KST)


def _contains_term(text: str, term: str) -> bool:
    t = _compact(term)
    if not t or len(t) < 2:
        return False
    return t in _compact(text)


def _first_matching_term(title: str, desc: str, terms: list[str]) -> str:
    for term in terms:
        if _contains_term(title, term) or _contains_term(desc, term):
            return term
    return ""


def is_theme_title(title: str) -> bool:
    t = strip_html(title)
    return any(kw in t for kw in TITLE_THEME_KEYWORDS)


def is_multi_stock_roundup(title: str, description: str) -> bool:
    title_c = _compact(title)
    if not title_c:
        return False
    desc = str(description or "")
    if not desc:
        return False
    if re.search(r"[가-힣A-Za-z0-9]{2,12}(?:,|、)\s*[가-힣A-Za-z0-9]{2,12}(?:,|、)", desc):
        segments = re.split(r"[,、]", desc)
        named = sum(
            1
            for seg in segments
            if 2 <= len(seg.strip()) <= 14 and re.search(r"[가-힣]", seg)
        )
        if named >= 3:
            return True
    if " 등 " in desc or desc.rstrip().endswith("등") or " 등이" in desc:
        if desc.count(",") >= 2 or desc.count("、") >= 2:
            return True
    return False


def is_homonym_noise(symbol: str, title: str, description: str) -> bool:
    patterns = HOMONYM_NOISE_PATTERNS.get(symbol)
    if not patterns:
        return False
    blob = f"{title} {description}"
    if not any(p in blob for p in patterns):
        return False
    hints = HOMONYM_STRONG_HINTS.get(symbol, ())
    return not any(h in blob for h in hints)


def analyze_match(
    item: dict[str, Any],
    *,
    symbol: str,
    terms: list[str] | None = None,
) -> MatchInfo:
    title = str(item.get("title") or "")
    desc = str(item.get("description") or "")
    terms = terms or match_terms_for_symbol(symbol)

    matched_term = _first_matching_term(title, desc, terms)
    if not matched_term and symbol:
        if _contains_term(title, symbol) or _contains_term(desc, symbol):
            matched_term = symbol

    direct_title = bool(matched_term and _contains_term(title, matched_term))
    desc_only = bool(matched_term and not direct_title and _contains_term(desc, matched_term))
    title_lead = False
    if matched_term and direct_title:
        lead = strip_html(title)[:TITLE_LEAD_CHARS]
        title_lead = _contains_term(lead, matched_term)

    theme = is_theme_title(title)
    roundup = bool(desc_only and is_multi_stock_roundup(title, desc))
    noise = is_homonym_noise(symbol, title, desc)

    matched = bool(matched_term) and not noise
    if (
        len(_compact(symbol)) <= SHORT_SYMBOL_MAX_LEN
        and matched
        and not direct_title
        and not any(_contains_term(title, t) or _contains_term(desc, t) for t in terms if t != symbol)
    ):
        matched = False

    return MatchInfo(
        matched=matched,
        matched_term=matched_term,
        direct_title_match=direct_title,
        title_lead_match=title_lead,
        description_only_match=desc_only,
        theme_article=theme,
        multi_stock_roundup=roundup,
        possible_name_noise=noise,
    )


def news_relevance_score(
    item: dict[str, Any],
    *,
    symbol: str,
    sector_kw: str,
    now: datetime | None = None,
    match: MatchInfo | None = None,
) -> int:
    now = now or _kst_now()
    match = match or analyze_match(item, symbol=symbol)
    if not match.matched:
        return -999

    title = str(item.get("title") or "")
    desc = str(item.get("description") or "")
    blob = f"{title} {desc}"

    score = 0
    if match.direct_title_match:
        score += 30
    elif match.description_only_match:
        score += 10
    if match.title_lead_match:
        score += 20
    if sector_kw and sector_kw in blob:
        score += 15
    if any(kw in blob for kw in NEWS_TOPIC_KEYWORDS):
        score += 10

    pub = parse_pub_date(str(item.get("pubDate") or item.get("pub_date") or ""))
    if pub and (now - pub).days <= 7:
        score += 10

    if match.multi_stock_roundup:
        score -= 20
    if match.theme_article:
        score -= 15
    if match.possible_name_noise:
        score -= 40
    return score


def build_quality_flags(match: MatchInfo, *, domain_limited: bool = False) -> dict[str, bool]:
    return {
        "direct_title_match": match.direct_title_match,
        "description_only_match": match.description_only_match,
        "theme_article": match.theme_article,
        "possible_name_noise": match.possible_name_noise,
        "domain_limited": domain_limited,
    }


def extract_news_domain(item: dict[str, Any]) -> str:
    for key in ("originallink", "link"):
        url = str(item.get(key) or "").strip()
        if not url:
            continue
        try:
            host = urlparse(url).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            return host
        except Exception:
            continue
    return ""


def _dedupe_key(item: dict[str, Any]) -> tuple[str, str]:
    for key in ("link", "originallink"):
        url = str(item.get(key) or "").strip().lower()
        if url:
            return ("url", url)
    return ("title", normalize_title(str(item.get("title", ""))))


def select_top_with_domain_cap(
    candidates: list[dict[str, Any]],
    *,
    top_n: int = NEWS_TOP_N,
    max_per_domain: int = MAX_PER_DOMAIN,
) -> list[dict[str, Any]]:
    """점수 순 선택 + 동일 도메인 최대 max_per_domain (초과분은 제외)."""
    if not candidates:
        return []

    pool = sorted(
        candidates,
        key=lambda x: (
            -int(x.get("relevance_score") or 0),
            str(x.get("pubDate") or ""),
        ),
    )
    selected: list[dict[str, Any]] = []

    for item in pool:
        if len(selected) >= top_n:
            break
        domain = str(item.get("domain") or "")
        same = sum(1 for s in selected if str(s.get("domain") or "") == domain and domain)
        if domain and same >= max_per_domain:
            flags = dict(item.get("quality_flags") or {})
            flags["domain_limited"] = True
            continue
        selected.append(item)

    return selected[:top_n]


def filter_and_rank_news(
    items: list[dict[str, Any]],
    *,
    symbol: str,
    sector_kw: str,
    max_age_days: int = NEWS_MAX_AGE_DAYS,
    top_n: int = NEWS_TOP_N,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or _kst_now()
    cutoff = now - timedelta(days=max_age_days)
    seen: set[tuple[str, str]] = set()
    terms = match_terms_for_symbol(symbol)
    candidates: list[dict[str, Any]] = []

    for raw in items:
        match = analyze_match(raw, symbol=symbol, terms=terms)
        if not match.matched:
            continue

        pub = parse_pub_date(str(raw.get("pubDate") or ""))
        if pub and pub < cutoff:
            continue

        key = _dedupe_key(raw)
        if key in seen:
            continue
        seen.add(key)

        score = news_relevance_score(
            raw, symbol=symbol, sector_kw=sector_kw, now=now, match=match
        )
        candidates.append(
            {
                **raw,
                "relevance_score": score,
                "quality_flags": build_quality_flags(match),
                "domain": extract_news_domain(raw),
                "matched_term": match.matched_term,
            }
        )

    return select_top_with_domain_cap(candidates, top_n=top_n)


def _normalize_news_item(row: dict[str, Any], query: str) -> dict[str, Any] | None:
    title = strip_html(str(row.get("title", "")))
    if not title:
        return None
    return {
        "title": title,
        "description": strip_html(str(row.get("description", ""))),
        "pubDate": str(row.get("pubDate", "")).strip(),
        "link": str(row.get("link", "")).strip(),
        "originallink": str(row.get("originallink", "")).strip(),
        "query": query,
        "source": "naver_search_news",
    }


def collect_naver_news_for_stock(
    symbol: str,
    sector: str,
    *,
    ticker: str | None = None,
    display: int = NEWS_DISPLAY,
    max_age_days: int = NEWS_MAX_AGE_DAYS,
    top_n: int = NEWS_TOP_N,
) -> list[dict[str, Any]]:
    sector_kw = sector_keyword(sector)
    queries = search_queries_for_symbol(symbol, sector, ticker=ticker)

    merged: list[dict[str, Any]] = []
    for q in queries:
        for row in search_raw_news(q, display=display):
            norm = _normalize_news_item(row, q)
            if norm:
                merged.append(norm)

    ranked = filter_and_rank_news(
        merged,
        symbol=symbol,
        sector_kw=sector_kw,
        max_age_days=max_age_days,
        top_n=top_n,
    )
    terms = match_terms_for_symbol(symbol, ticker=ticker)
    return [
        {
            "title": i["title"],
            "description": i["description"],
            "pubDate": i["pubDate"],
            "link": i["link"],
            "originallink": i.get("originallink", ""),
            "relevance_score": i.get("relevance_score", 0),
            "quality_flags": i.get(
                "quality_flags",
                build_quality_flags(analyze_match(i, symbol=symbol, terms=terms)),
            ),
            "matched_term": i.get("matched_term", ""),
            "query": i.get("query", ""),
            "source": "naver_search_news",
        }
        for i in ranked
    ]
