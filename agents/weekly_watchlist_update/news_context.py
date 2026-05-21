"""MVP 3-2~3-5 — 뉴스/공시 judgment 연결·태깅·Slack/MD·LLM 요약."""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.weekly_watchlist_update.news_collect import match_terms_for_symbol

from agents.kr_intraday_slack.llm_client import call_primary_json, is_primary_configured
from agents.weekly_watchlist_update.weekly_review import (
    ACTION_KEEP,
    ACTION_REMOVE,
    REASON_CAUTION,
    REMOVE_LEVEL_STRONG,
)

from .stock_news import NEWS_DIR

logger = logging.getLogger("weekly_watchlist.news_context")

SLACK_ISSUE_MAX_LEN = 45
MAX_LLM_NEWS_SUMMARY_STOCKS = 12
NEWS_BEATS_DART_MIN_SCORE = 55
TITLE_LEAD_DIRECT_CHARS = 30
MIN_PEER_NAME_LEN = 3

_WATCHLIST_PEER_NAMES: list[str] | None = None

RISK_DART_KEYWORDS = ("소송",)

# (부분문자열 키워드들, 정규화 라벨) — 긴/구체 패턴 우선
DART_TITLE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("연결재무제표기준영업(잠정)실적", "연결재무제표기준영업잠정실적"), "잠정 실적 발표"),
    (("영업(잠정)실적(공정공시)", "영업잠정실적"), "잠정 실적 발표"),
    (("[기재정정]단일판매", "기재정정단일판매"), "공급계약 정정"),
    (("단일판매ㆍ공급계약", "단일판매·공급계약"), "공급계약 체결"),
    (("신규시설투자등", "신규시설투자"), "신규시설투자"),
    (("주요사항보고서(자기주식취득", "자기주식취득결정"), "자기주식 취득"),
    (("주요사항보고서(자기주식처분", "자기주식처분결정"), "자기주식 처분"),
    (("자기주식처분결과",), "자기주식 처분 결과"),
    (("최대주주변경을수반하는주식담보", "주식담보제공계약"), "최대주주 관련 담보계약"),
    (("소송등의제기", "소송등의제기ㆍ신청"), "소송 제기"),
)

VAGUE_DART_NORMALIZED = frozenset({"영업", "실적", "공시"})

TAG_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("단일판매", "공급계약"), ("수주", "공시")),
    (("신규시설투자",), ("증설", "투자", "공시")),
    (("잠정실적", "영업", "실적"), ("실적", "공시")),
    (("자기주식",), ("자기주식", "공시")),
    (("목표주가", "목표가"), ("목표가", "리포트")),
    (("기관 순매수", "외국인 순매수", "순매수"), ("수급",)),
    (("소송",), ("소송", "공시")),
    (("HBM",), ("HBM", "반도체")),
    (("LNG", "보냉재"), ("LNG", "조선")),
    (("방산", "수주잔고"), ("방산",)),
    (("유상증자", "전환사채"), ("공시", "투자")),
)

SECTOR_TAG_HINTS: tuple[tuple[str, str], ...] = (
    ("반도체", "반도체"),
    ("조선", "조선"),
    ("방산", "방산"),
    ("LNG", "LNG"),
)


def _compact_key(text: str) -> str:
    t = html.unescape(str(text or ""))
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\s+", "", t)
    return t


def clean_display_text(text: str) -> str:
    """HTML entity·태그 제거 후 표시용 문자열."""
    t = html.unescape(str(text or ""))
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_dart_issue_title(report_nm: str) -> str:
    """DART report_nm → Slack/MD용 짧은 한글 라벨."""
    raw = clean_display_text(report_nm)
    if not raw:
        return "공시"

    compact = _compact_key(raw)
    for patterns, label in DART_TITLE_RULES:
        if any(p in compact or p in raw for p in patterns):
            return label

    # [기재정정] 등 접두 제거 후 재시도
    stripped = re.sub(r"^\[[^\]]+\]", "", raw).strip()
    if stripped != raw:
        inner = normalize_dart_issue_title(stripped)
        if inner not in VAGUE_DART_NORMALIZED:
            return inner

    # 괄호 안 요약 (주요사항보고서(자기주식…))
    paren = re.search(r"\(([^)]+)\)", raw)
    if paren:
        inner = clean_display_text(paren.group(1))
        if "자기주식" in inner and "취득" in inner:
            return "자기주식 취득"
        if "자기주식" in inner and "처분" in inner:
            return "자기주식 처분"

    if compact in VAGUE_DART_NORMALIZED or raw in VAGUE_DART_NORMALIZED:
        return "실적·영업 공시"

    # ㆍ → 공백, 긴 붙여쓰기 일부 분리
    spaced = raw.replace("ㆍ", " ").replace("·", " ")
    if len(spaced) > 24:
        return spaced[:24].rstrip() + "…"
    return spaced


def stock_news_path(as_of_date: str) -> Path:
    return NEWS_DIR / f"stock_news_{as_of_date}.json"


def load_stock_news(as_of_date: str) -> dict[str, Any] | None:
    path = stock_news_path(as_of_date)
    if not path.is_file():
        logger.warning("[NEWS] 파일 없음: %s", path.name)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("[NEWS] JSON 형식 오류: %s", path.name)
            return None
        return data
    except Exception as exc:
        logger.warning("[NEWS] JSON 파싱 실패: %s", type(exc).__name__)
        return None


def _news_by_ticker(news_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in news_data.get("stocks") or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("ticker", "")).strip().zfill(6)
        if code:
            out[code] = row
    return out


def _sanitize_news_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                **row,
                "title": clean_display_text(str(row.get("title", ""))),
                "description": clean_display_text(str(row.get("description", ""))),
            }
        )
    return out


def _sanitize_dart_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        raw_nm = str(row.get("report_nm", ""))
        out.append(
            {
                **row,
                "report_nm": clean_display_text(raw_nm),
                "report_nm_normalized": normalize_dart_issue_title(raw_nm),
            }
        )
    return out


def collect_issue_tags(
    naver_news: list[dict[str, Any]],
    dart_disclosures: list[dict[str, Any]],
    *,
    sector: str = "",
) -> list[str]:
    blob_parts: list[str] = []
    for n in naver_news:
        blob_parts.append(str(n.get("title", "")))
        blob_parts.append(str(n.get("description", "")))
    for d in dart_disclosures:
        blob_parts.append(str(d.get("report_nm", "")))
        blob_parts.extend(str(k) for k in (d.get("matched_keywords") or []))
    blob = " ".join(blob_parts)

    tags: list[str] = []
    seen: set[str] = set()
    for patterns, tag_set in TAG_RULES:
        if any(p in blob for p in patterns):
            for t in tag_set:
                if t not in seen:
                    seen.add(t)
                    tags.append(t)
    for hint, tag in SECTOR_TAG_HINTS:
        if hint in sector or hint in blob:
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    topic_words = ("실적", "수주", "공시", "증설", "투자", "목표가", "리포트", "AI")
    for w in topic_words:
        if w in blob and w not in seen:
            seen.add(w)
            tags.append(w)
    return tags


@dataclass(frozen=True)
class DirectNewsInfo:
    direct: bool
    strong_direct: bool
    description_only: bool
    possible_indirect_mention: bool


def _load_watchlist_peer_names() -> list[str]:
    global _WATCHLIST_PEER_NAMES
    if _WATCHLIST_PEER_NAMES is not None:
        return _WATCHLIST_PEER_NAMES
    try:
        from data.kr_watchlist import iter_watchlist_entries

        names: list[str] = []
        for entry in iter_watchlist_entries():
            name = str(entry.get("name", "")).strip()
            if len(name) >= MIN_PEER_NAME_LEN:
                names.append(name)
        _WATCHLIST_PEER_NAMES = sorted(set(names), key=len, reverse=True)
    except Exception:
        _WATCHLIST_PEER_NAMES = []
    return _WATCHLIST_PEER_NAMES


def _watchlist_peer_names(exclude_symbol: str) -> list[str]:
    sym = str(exclude_symbol or "").strip()
    return [n for n in _load_watchlist_peer_names() if n != sym]


def _term_position_in_text(text: str, term: str) -> int | None:
    compact_text = _compact_key(text)
    compact_term = _compact_key(term)
    if len(compact_term) < 2:
        return None
    idx = compact_text.find(compact_term)
    return idx if idx >= 0 else None


def _term_in_title_lead(title: str, term: str, *, lead_chars: int = TITLE_LEAD_DIRECT_CHARS) -> bool:
    lead = clean_display_text(title)[:lead_chars]
    return _term_position_in_text(lead, term) is not None


def is_direct_news_for_stock(
    item: dict[str, Any],
    stock: dict[str, Any] | None = None,
    *,
    symbol: str = "",
    ticker: str | None = None,
    peer_names: list[str] | None = None,
) -> DirectNewsInfo:
    """
    Slack top_issue용 직접성 판별.
    title에 symbol/alias 없으면 direct=False.
    title에 다른 watchlist 종목이 먼저 나오면 possible_indirect_mention.
    """
    if stock:
        symbol = str(stock.get("symbol") or symbol or "")
        ticker = str(stock.get("ticker") or ticker or "") or None

    title = clean_display_text(str(item.get("title") or ""))
    desc = clean_display_text(str(item.get("description") or ""))
    sym = str(symbol or "").strip()
    code = str(ticker or "").strip().zfill(6) if ticker else None
    terms = match_terms_for_symbol(sym, ticker=code) if sym else []

    own_title_positions: list[int] = []
    for term in terms:
        pos = _term_position_in_text(title, term)
        if pos is not None:
            own_title_positions.append(pos)

    direct = bool(own_title_positions)
    strong_direct = direct and any(_term_in_title_lead(title, t) for t in terms)

    desc_only = False
    if not direct and terms:
        desc_only = any(
            _term_position_in_text(desc, t) is not None for t in terms
        )

    possible_indirect = False
    peers = peer_names if peer_names is not None else _watchlist_peer_names(sym)
    own_first = min(own_title_positions) if own_title_positions else None

    for peer in peers:
        peer_pos = _term_position_in_text(title, peer)
        if peer_pos is None:
            continue
        if own_first is None or peer_pos < own_first:
            possible_indirect = True
            break

    if not direct and desc_only:
        for peer in peers:
            if _term_position_in_text(title, peer) is not None:
                possible_indirect = True
                break

    flags = item.get("quality_flags") or {}
    if flags.get("possible_name_noise"):
        possible_indirect = True
    if flags.get("theme_article") and not strong_direct:
        possible_indirect = True
    if flags.get("description_only_match") and not direct:
        possible_indirect = True

    return DirectNewsInfo(
        direct=direct and not possible_indirect,
        strong_direct=strong_direct and not possible_indirect,
        description_only=desc_only and not direct,
        possible_indirect_mention=possible_indirect,
    )


def _dart_is_risk(dart: dict[str, Any]) -> bool:
    name = str(dart.get("report_nm") or "")
    kws = dart.get("matched_keywords") or []
    return any(k in name for k in RISK_DART_KEYWORDS) or any(
        k in RISK_DART_KEYWORDS for k in kws
    )


def _dart_candidate_score(dart: dict[str, Any]) -> int:
    risk = _dart_is_risk(dart)
    if risk:
        return 1000
    label = str(dart.get("report_nm_normalized") or normalize_dart_issue_title(
        str(dart.get("report_nm", ""))
    ))
    score = 700
    if label in VAGUE_DART_NORMALIZED:
        score = 450
    kws = dart.get("matched_keywords") or []
    score += min(len(kws) * 15, 45)
    return score


def _news_rank_score(
    news: dict[str, Any],
    info: DirectNewsInfo,
) -> int:
    rel = int(news.get("relevance_score") or 0)
    if info.possible_indirect_mention or not info.direct:
        if info.description_only:
            return rel - 200
        return -999
    score = rel + (80 if info.strong_direct else 40)
    flags = news.get("quality_flags") or {}
    if flags.get("theme_article"):
        score -= 30
    return score


def _build_dart_issue(dart: dict[str, Any]) -> dict[str, Any]:
    raw_nm = str(dart.get("report_nm") or "")
    label = str(dart.get("report_nm_normalized") or normalize_dart_issue_title(raw_nm))
    dt = str(dart.get("rcept_dt") or "")
    if len(dt) == 8:
        dt = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}"
    return {
        "kind": "dart",
        "title": clean_display_text(raw_nm),
        "title_normalized": label,
        "date": dt,
        "risk_issue": _dart_is_risk(dart),
        "source": "opendart",
    }


def _build_news_issue(
    news: dict[str, Any],
    *,
    symbol: str = "",
    ticker: str | None = None,
    info: DirectNewsInfo | None = None,
    sector_style: bool = False,
    slack_omit: bool = False,
) -> dict[str, Any]:
    info = info or is_direct_news_for_stock(
        news, symbol=symbol, ticker=ticker
    )
    flags = news.get("quality_flags") or {}
    return {
        "kind": "news",
        "title": clean_display_text(str(news.get("title") or "")),
        "relevance_score": int(news.get("relevance_score") or 0),
        "direct_title_match": info.direct,
        "strong_direct": info.strong_direct,
        "description_only_match": info.description_only,
        "theme_article": bool(flags.get("theme_article")),
        "possible_indirect_mention": info.possible_indirect_mention,
        "sector_style": sector_style,
        "slack_omit": slack_omit,
        "source": "naver_search_news",
    }


def select_top_issue(
    naver_news: list[dict[str, Any]],
    dart_disclosures: list[dict[str, Any]],
    *,
    symbol: str = "",
    ticker: str | None = None,
) -> dict[str, Any] | None:
    """
    Slack top_issue 우선순위:
    1) 리스크 DART
    2) 제목 직접 뉴스 + relevance >= 55 (일반 DART보다 우선)
    3) 일반 DART
    4) 제목 직접 뉴스 (점수 무관)
    5) description-only/간접 뉴스 — Slack 생략 (MD용 naver 목록은 유지)
    """
    risk_darts = [d for d in dart_disclosures if isinstance(d, dict) and _dart_is_risk(d)]
    if risk_darts:
        return _build_dart_issue(risk_darts[0])

    peers = _watchlist_peer_names(symbol)
    direct_news: list[tuple[dict[str, Any], DirectNewsInfo, int]] = []
    desc_only_news: list[tuple[dict[str, Any], DirectNewsInfo, int]] = []

    for news in naver_news:
        if not isinstance(news, dict):
            continue
        info = is_direct_news_for_stock(
            news, symbol=symbol, ticker=ticker, peer_names=peers
        )
        score = _news_rank_score(news, info)
        if info.possible_indirect_mention and not info.direct:
            continue
        if info.direct:
            direct_news.append((news, info, score))
        elif info.description_only:
            desc_only_news.append((news, info, score))

    direct_news.sort(key=lambda x: -x[2])
    desc_only_news.sort(key=lambda x: -x[2])

    non_risk_darts = [
        d for d in dart_disclosures if isinstance(d, dict) and not _dart_is_risk(d)
    ]

    if direct_news:
        best_news, best_info, _ = direct_news[0]
        rel = int(best_news.get("relevance_score") or 0)
        if rel >= NEWS_BEATS_DART_MIN_SCORE and best_info.direct:
            return _build_news_issue(
                best_news, symbol=symbol, ticker=ticker, info=best_info
            )

    if non_risk_darts:
        return _build_dart_issue(non_risk_darts[0])

    if direct_news:
        best_news, best_info, _ = direct_news[0]
        return _build_news_issue(
            best_news, symbol=symbol, ticker=ticker, info=best_info
        )

    if desc_only_news:
        best_news, best_info, _ = desc_only_news[0]
        return _build_news_issue(
            best_news,
            symbol=symbol,
            ticker=ticker,
            info=best_info,
            sector_style=True,
            slack_omit=True,
        )

    return None


def select_top_issue_for_slack(stock: dict[str, Any]) -> dict[str, Any] | None:
    ctx = stock.get("news_context") or {}
    return ctx.get("top_issue")


def _truncate_issue(text: str, max_len: int = SLACK_ISSUE_MAX_LEN) -> str:
    t = clean_display_text(text)
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def format_issue_line_rule_based(top_issue: dict[str, Any] | None) -> str | None:
    if not top_issue:
        return None
    kind = top_issue.get("kind")
    if kind == "dart":
        label = str(
            top_issue.get("title_normalized")
            or normalize_dart_issue_title(str(top_issue.get("title") or ""))
        )
        prefix = "리스크 공시: " if top_issue.get("risk_issue") else "공시: "
        return _truncate_issue(prefix + label)
    if kind == "news":
        title = clean_display_text(str(top_issue.get("title") or ""))
        if not title:
            return None
        if top_issue.get("sector_style") or top_issue.get("description_only_match"):
            return _truncate_issue(f"섹터 뉴스: {title}")
        return _truncate_issue(f"뉴스: {title}")
    return None


def format_slack_issue_line(news_context: dict[str, Any] | None) -> str | None:
    if not news_context:
        return None
    top = news_context.get("top_issue")
    if isinstance(top, dict) and top.get("slack_omit"):
        return None
    line = news_context.get("issue_summary_line")
    if line:
        return _truncate_issue(clean_display_text(str(line)))
    llm = news_context.get("issue_summary")
    if llm:
        return _truncate_issue(clean_display_text(str(llm)))
    return format_issue_line_rule_based(news_context.get("top_issue"))


def build_news_context_for_stock(
    stock_news_row: dict[str, Any] | None,
    *,
    sector: str = "",
    symbol: str = "",
) -> dict[str, Any]:
    if not stock_news_row:
        return {
            "naver_news": [],
            "dart_disclosures": [],
            "top_issue": None,
            "issue_tags": [],
        }
    naver = _sanitize_news_items(list(stock_news_row.get("naver_news") or []))
    dart = _sanitize_dart_items(list(stock_news_row.get("dart_disclosures") or []))
    sym = symbol or str(stock_news_row.get("symbol") or "")
    code = str(stock_news_row.get("ticker") or "").strip().zfill(6) or None
    tags = collect_issue_tags(naver, dart, sector=sector)
    top = select_top_issue(naver, dart, symbol=sym, ticker=code)
    return {
        "naver_news": naver,
        "dart_disclosures": dart,
        "top_issue": top,
        "issue_tags": tags,
    }


def attach_news_to_judgments(
    judgment: dict[str, Any],
    news_data: dict[str, Any] | None,
) -> dict[str, Any]:
    by_ticker = _news_by_ticker(news_data) if news_data else {}
    stocks = judgment.get("stocks") or []
    attached = 0
    with_issue = 0

    for stock in stocks:
        if not isinstance(stock, dict):
            continue
        ticker = str(stock.get("ticker", "")).strip().zfill(6)
        symbol = str(stock.get("symbol") or "")
        row = by_ticker.get(ticker)
        if not row and symbol:
            for v in by_ticker.values():
                if str(v.get("symbol", "")) == symbol:
                    row = v
                    break
        sector = str(stock.get("sector") or (stock.get("metrics") or {}).get("sector") or "")
        ctx = build_news_context_for_stock(row, sector=sector, symbol=symbol)
        stock["news_context"] = ctx
        if row:
            attached += 1
        if ctx.get("top_issue"):
            with_issue += 1
        ctx["issue_summary_line"] = format_slack_issue_line(ctx)

    judgment["news_attached_count"] = attached
    judgment["news_with_issue_count"] = with_issue
    return judgment


def log_news_pipeline_stats(
    news_data: dict[str, Any] | None,
    judgment: dict[str, Any],
    *,
    llm_skipped: bool = False,
) -> None:
    sources = (news_data or {}).get("sources") or {}
    naver_cfg = sources.get("naver_news") or {}
    dart_cfg = sources.get("dart_disclosures") or {}
    logger.info(
        "[NEWS] configured: naver=%s dart=%s",
        not naver_cfg.get("skipped", True),
        not dart_cfg.get("skipped", True),
    )
    news_items = 0
    dart_items = 0
    for row in (news_data or {}).get("stocks") or []:
        news_items += len(row.get("naver_news") or [])
        dart_items += len(row.get("dart_disclosures") or [])
    logger.info(
        "[NEWS] collected stocks=%d news_items=%d dart_items=%d",
        len((news_data or {}).get("stocks") or []),
        news_items,
        dart_items,
    )
    logger.info(
        "[NEWS] attached judgments=%d with_issue=%d",
        judgment.get("news_attached_count", 0),
        judgment.get("news_with_issue_count", 0),
    )
    if llm_skipped:
        logger.info("[NEWS] llm_summary skipped (--no-llm)")


def _llm_summary_targets(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = sorted(
        [s for s in stocks if s.get("action") == ACTION_KEEP],
        key=lambda x: -int(x.get("priority_score") or 0),
    )
    strong = [s for s in stocks if s.get("remove_level") == REMOVE_LEVEL_STRONG]
    caution = [s for s in stocks if s.get("reason_code") == REASON_CAUTION]
    dart_hits = [
        s for s in stocks if (s.get("news_context") or {}).get("dart_disclosures")
    ]

    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in (keep[:5], strong, caution, dart_hits):
        for s in group:
            t = str(s.get("ticker", "")).zfill(6)
            if t and t not in seen:
                seen.add(t)
                ordered.append(s)
            if len(ordered) >= MAX_LLM_NEWS_SUMMARY_STOCKS:
                return ordered
    return ordered[:MAX_LLM_NEWS_SUMMARY_STOCKS]


def _stock_llm_input(stock: dict[str, Any]) -> dict[str, Any]:
    ctx = stock.get("news_context") or {}
    news_titles = [
        {
            "title": clean_display_text(str(n.get("title", ""))),
            "description": clean_display_text(str(n.get("description", "")))[:120],
        }
        for n in (ctx.get("naver_news") or [])[:3]
    ]
    dart_items = [
        {
            "report_nm": d.get("report_nm"),
            "report_nm_normalized": d.get("report_nm_normalized"),
            "matched_keywords": d.get("matched_keywords"),
        }
        for d in (ctx.get("dart_disclosures") or [])[:3]
    ]
    return {
        "ticker": stock.get("ticker"),
        "symbol": stock.get("symbol"),
        "action": stock.get("action"),
        "reason_code": stock.get("reason_code"),
        "remove_level": stock.get("remove_level"),
        "one_line": stock.get("one_line"),
        "issue_tags": ctx.get("issue_tags"),
        "naver_news": news_titles,
        "dart_disclosures": dart_items,
    }


def build_news_summary_prompt(batch: list[dict[str, Any]], as_of_date: str) -> str:
    payload = json.dumps(batch, ensure_ascii=False, indent=2)
    return f"""기준일 {as_of_date}. 아래 종목별 뉴스·공시 요약만 JSON 배열로 반환하세요.

각 원소:
{{"ticker":"6자리","symbol":"종목명","issue_summary":"한 줄 80자 이내","issue_tone":"positive|negative|mixed|neutral","confidence":"high|medium|low"}}

원문 전체가 아닌 제공된 title/description/report_nm만 참고. 가격 판단 one_line과 뉴스를 연결해 mixed도 명시.

입력:
{payload}
"""


def apply_llm_news_summaries(
    judgment: dict[str, Any],
    summaries: list[dict[str, Any]],
) -> None:
    by_ticker = {
        str(s.get("ticker", "")).zfill(6): s for s in summaries if isinstance(s, dict)
    }
    for stock in judgment.get("stocks") or []:
        t = str(stock.get("ticker", "")).zfill(6)
        row = by_ticker.get(t)
        if not row:
            continue
        ctx = stock.setdefault("news_context", {})
        summary = clean_display_text(str(row.get("issue_summary") or ""))
        if summary:
            ctx["issue_summary"] = summary
            ctx["issue_tone"] = row.get("issue_tone") or "neutral"
            ctx["issue_summary_confidence"] = row.get("confidence") or "medium"
            ctx["issue_summary_line"] = _truncate_issue(summary)


def run_news_llm_summaries(
    judgment: dict[str, Any],
    *,
    as_of_date: str,
    use_llm: bool = True,
) -> dict[str, Any]:
    if not use_llm:
        judgment["news_llm_used"] = False
        return judgment
    if not is_primary_configured():
        judgment["news_llm_used"] = False
        return judgment

    stocks = judgment.get("stocks") or []
    targets = _llm_summary_targets(stocks)
    if not targets:
        judgment["news_llm_used"] = False
        return judgment

    batch = [_stock_llm_input(s) for s in targets]
    prompt = build_news_summary_prompt(batch, as_of_date)
    parsed, err = call_primary_json(prompt, agent="weekly_watchlist_news_summary")
    if not parsed:
        logger.warning("[NEWS] LLM 요약 실패, rule fallback: %s", err)
        judgment["news_llm_used"] = False
        judgment["news_llm_error"] = err
        return judgment

    items = parsed if isinstance(parsed, list) else parsed.get("summaries") or parsed.get("stocks")
    if not isinstance(items, list):
        judgment["news_llm_used"] = False
        return judgment

    apply_llm_news_summaries(judgment, items)
    judgment["news_llm_used"] = True
    judgment["news_llm_summary_count"] = len(items)
    return judgment


def build_next_week_checkpoints(
    judgment: dict[str, Any],
    sector_mood: dict[str, str],
) -> list[str]:
    lines: list[str] = []
    mood = sector_mood or judgment.get("sector_mood") or {}
    if any("반도체" in s for s in mood):
        lines.append("반도체 소재/장비: 거래대금 회복 여부 확인")
    if any(k in s and mood.get(s) == "weak" for s in mood for k in ("조선", "LNG")):
        lines.append("조선/LNG: 수주·공시 모멘텀 지속 여부 확인")
    if any("방산" in s for s in mood):
        lines.append("방산/우주: 수주잔고·해외계약 뉴스 확인")
    strong_n = int(judgment.get("strong_remove_count") or 0)
    if strong_n:
        lines.append("strong_remove 종목은 반등 전까지 신규 진입 보류")
    tags_seen: set[str] = set()
    for stock in judgment.get("stocks") or []:
        for tag in (stock.get("news_context") or {}).get("issue_tags") or []:
            tags_seen.add(tag)
    if "HBM" in tags_seen:
        lines.append("HBM 관련 종목: 메모리 업황·공시 교차 확인")
    if not lines:
        lines.append("섹터 거래대금·RS 추이를 주간 단위로 재확인")
    return lines
