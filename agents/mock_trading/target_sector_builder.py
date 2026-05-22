# -*- coding: utf-8 -*-
"""사업 근거 기반 장기 산업 종목풀 (가격 필터 없음)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.business_sector_classifier import (
    MANDATORY_REVIEW_TICKERS,
    classify_from_business_text,
    classify_watchlist_entry,
)
from agents.mock_trading.models import SECTOR_GROUPS, SECTOR_KEYWORDS, SECTOR_LABELS
from agents.mock_trading.naver_company_profile import get_or_fetch_profiles
from agents.mock_trading.universe_builder import (
    classify_sector_groups,
    list_kosdaq_tickers,
    ticker_name_map,
)
from data.kr_market import get_trading_date
from data.kr_watchlist import iter_watchlist_entries

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

SECTOR_JSON_META: list[dict[str, str]] = [
    {
        "sector_key": "ai_semiconductor_material_equipment",
        "sector_name": "AI 반도체 소재·부품·장비",
    },
    {
        "sector_key": "power_technology",
        "sector_name": "전력기술",
    },
    {
        "sector_key": "industrial_robot_equipment",
        "sector_name": "산업·로봇 장비",
    },
]


def _pykrx_krx_industry_map(trading_date: str) -> dict[str, str]:
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception:
        return {}
    try:
        classified = pykrx_stock.get_market_sector_classifications(
            trading_date, market="KOSDAQ"
        )
    except Exception:
        return {}
    out: dict[str, str] = {}
    for ticker in classified.index.tolist():
        code = str(ticker).zfill(6)
        out[code] = str(classified.loc[ticker, "업종명"]).strip()
    return out


def _old_keyword_matched_tickers(names: dict[str, str]) -> dict[str, list[str]]:
    """종목명 키워드 1차 매칭 (discovery_hint 용, 최종 포함 아님)."""
    out: dict[str, list[str]] = {}
    for code, name in names.items():
        groups = classify_sector_groups(name)
        if groups:
            out[code] = groups
    return out


def _stock_record(
    *,
    ticker: str,
    name: str,
    sector_keys: list[str],
    business_summary: str,
    inclusion_reason: str,
    evidence_type: str,
    evidence_summary: str,
    classification_confidence: str,
    discovery_hint_keywords: list[str],
    review_status: str,
) -> dict[str, Any]:
    return {
        "ticker": ticker.zfill(6),
        "name": name,
        "market": "KOSDAQ",
        "sector_keys": sector_keys,
        "business_summary": business_summary[:500],
        "inclusion_reason": inclusion_reason[:500],
        "evidence_type": evidence_type,
        "evidence_summary": evidence_summary[:500],
        "classification_confidence": classification_confidence,
        "discovery_hint_keywords": discovery_hint_keywords,
        "review_status": review_status,
    }


def build_target_sector_universe(
    *,
    trading_date: str | None = None,
    refresh_profiles: bool = False,
    profile_delay_sec: float = 0.12,
    max_profile_fetch: int = 0,
) -> dict[str, Any]:
    """
    코스닥 전체 + 사업개요 기반 분류.
    가격·유동성 필터 미적용.
    """
    now = datetime.now(KST)
    date = trading_date or get_trading_date()

    tickers, list_err = list_kosdaq_tickers(date)
    names = ticker_name_map(tickers, date) if tickers else {}
    krx_map = _pykrx_krx_industry_map(date) if tickers else {}
    name_keyword_hits = _old_keyword_matched_tickers(names)

    errors: list[str] = []
    if list_err:
        errors.append(list_err)

    # 1) watchlist 검증 데이터 우선
    records: dict[str, dict[str, Any]] = {}
    for entry in iter_watchlist_entries():
        ticker = str(entry.get("ticker") or "").zfill(6)
        if not ticker or ticker == "000000":
            continue
        if ticker not in names:
            names[ticker] = str(entry.get("name") or ticker)
        cls = classify_watchlist_entry(entry)
        records[ticker] = _stock_record(
            ticker=ticker,
            name=str(entry.get("name") or names.get(ticker, ticker)),
            sector_keys=list(cls.get("sector_keys") or []),
            business_summary=str(cls.get("business_summary") or entry.get("business") or ""),
            inclusion_reason=str(cls.get("inclusion_reason") or ""),
            evidence_type=str(cls.get("evidence_type") or "existing_verified_data"),
            evidence_summary=str(cls.get("evidence_summary") or ""),
            classification_confidence=str(cls.get("classification_confidence") or "high"),
            discovery_hint_keywords=list(cls.get("discovery_hint_keywords") or []),
            review_status=str(cls.get("review_status") or "excluded"),
        )

    # 2) 네이버 기업개요 — watchlist 외 코스닥
    remaining = [t for t in tickers if t not in records]
    profiles = {}
    if remaining and not list_err:
        profiles = get_or_fetch_profiles(
            remaining,
            refresh=refresh_profiles,
            delay_sec=profile_delay_sec,
            max_fetch=max_profile_fetch,
        )

    for code in tickers:
        if code in records:
            continue
        name = names.get(code, code)
        business = profiles.get(code, "")
        evidence_type = "business_description" if business else "business_description"
        hints = _discovery_hint_keywords(name, name_keyword_hits.get(code))

        if not business:
            if code in MANDATORY_REVIEW_TICKERS:
                records[code] = _stock_record(
                    ticker=code,
                    name=name,
                    sector_keys=[],
                    business_summary="",
                    inclusion_reason="필수 검토 종목 — 기업개요 미수집, 수동·DART 보강 필요",
                    evidence_type=evidence_type,
                    evidence_summary=f"KRX:{krx_map.get(code, '')}",
                    classification_confidence="needs_review",
                    discovery_hint_keywords=hints,
                    review_status="needs_review",
                )
            elif hints:
                records[code] = _stock_record(
                    ticker=code,
                    name=name,
                    sector_keys=[],
                    business_summary="",
                    inclusion_reason="종목명 키워드만 매칭 — 사업개요 없어 최종 포함 불가",
                    evidence_type=evidence_type,
                    evidence_summary=f"KRX:{krx_map.get(code, '')}",
                    classification_confidence="needs_review",
                    discovery_hint_keywords=hints,
                    review_status="excluded",
                )
            continue

        cls = classify_from_business_text(
            business, name=name, krx_industry=krx_map.get(code, "")
        )
        review_status = str(cls.get("review_status") or "excluded")
        sector_keys = list(cls.get("sector_keys") or [])

        if code in MANDATORY_REVIEW_TICKERS and not sector_keys:
            review_status = "needs_review"
            cls["classification_confidence"] = "needs_review"

        records[code] = _stock_record(
            ticker=code,
            name=name,
            sector_keys=sector_keys,
            business_summary=business[:500],
            inclusion_reason=str(cls.get("inclusion_reason") or ""),
            evidence_type="business_description",
            evidence_summary=business[:500],
            classification_confidence=str(cls.get("classification_confidence") or "needs_review"),
            discovery_hint_keywords=hints,
            review_status=review_status,
        )

    # 필수 6종목: watchlist/naver 후에도 included 보장 (사업문구 있으면)
    for code in MANDATORY_REVIEW_TICKERS:
        if code not in records:
            records[code] = _stock_record(
                ticker=code,
                name=names.get(code, code),
                sector_keys=[],
                business_summary="",
                inclusion_reason="필수 검토 종목 — 코스닥 목록·프로필 미확인",
                evidence_type="business_description",
                evidence_summary="",
                classification_confidence="needs_review",
                discovery_hint_keywords=[],
                review_status="needs_review",
            )

    sectors_out: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for meta in SECTOR_JSON_META:
        sk = meta["sector_key"]
        bucket: list[dict[str, Any]] = []
        for rec in records.values():
            if sk not in rec.get("sector_keys", []):
                continue
            if rec.get("review_status") == "excluded":
                continue
            bucket.append(rec)
            if rec.get("review_status") == "included":
                counts[sk]["included"] += 1
            else:
                counts[sk]["needs_review"] += 1
        bucket.sort(key=lambda r: r["ticker"])
        sectors_out.append({**meta, "stocks": bucket})

    stats = _build_comparison_stats(records, name_keyword_hits, names)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "classification_method": "business_evidence_based",
        "trading_date": date,
        "sectors": sectors_out,
        "all_records": list(records.values()),
        "summary": {
            "kosdaq_total": len(tickers),
            "records_total": len(records),
            "sector_counts": {
                sk: {
                    "included": len(sec["stocks"]),
                    "needs_review": sum(
                        1
                        for r in records.values()
                        if sk in (r.get("sector_keys") or [])
                        and r.get("review_status") == "needs_review"
                    ),
                }
                for sk, sec in zip(
                    [m["sector_key"] for m in SECTOR_JSON_META],
                    sectors_out,
                )
            },
            **stats,
        },
        "errors": errors,
        "data_sources": {
            "pykrx_kosdaq_list": not bool(list_err),
            "pykrx_krx_industry": bool(krx_map),
            "kr_watchlist_verified": True,
            "naver_coinfo_business": bool(profiles) or refresh_profiles,
            "kis_price_filter_applied": False,
            "dart_company_profile": False,
            "naver_news_primary": False,
        },
    }


def _discovery_hint_keywords(name: str, groups: list[str] | None) -> list[str]:
    from agents.mock_trading.business_sector_classifier import _name_keyword_hints

    if groups:
        hints: list[str] = []
        for g in groups:
            for kw in SECTOR_KEYWORDS.get(g, ()):
                if kw.upper() in name.upper() or kw in name:
                    hints.append(kw)
        return sorted(set(hints))
    return _name_keyword_hints(name)


def _build_comparison_stats(
    records: dict[str, dict[str, Any]],
    name_keyword_hits: dict[str, list[str]],
    names: dict[str, str],
) -> dict[str, Any]:
    old_keyword_set = set(name_keyword_hits.keys())
    new_included = {
        t
        for t, r in records.items()
        if r.get("review_status") in ("included", "needs_review") and r.get("sector_keys")
    }
    weak_excluded = 0
    for code in old_keyword_set:
        rec = records.get(code, {})
        if rec.get("review_status") == "excluded":
            weak_excluded += 1

    missed_by_keyword = []
    for code, rec in records.items():
        if rec.get("review_status") == "included" and code not in old_keyword_set:
            missed_by_keyword.append(
                {"ticker": code, "name": rec.get("name"), "sector_keys": rec.get("sector_keys")}
            )

    mandatory: dict[str, dict[str, Any]] = {}
    for code in MANDATORY_REVIEW_TICKERS:
        rec = records.get(code, {})
        mandatory[code] = {
            "name": rec.get("name") or names.get(code, code),
            "sector_keys": rec.get("sector_keys"),
            "review_status": rec.get("review_status"),
            "classification_confidence": rec.get("classification_confidence"),
            "business_summary": (rec.get("business_summary") or "")[:120],
        }

    return {
        "old_keyword_matched_count": len(old_keyword_set),
        "old_keyword_weak_excluded_count": weak_excluded,
        "new_included_count": len(new_included),
        "missed_by_keyword_then_included": missed_by_keyword[:30],
        "mandatory_six": mandatory,
    }


def render_target_sector_review_md(payload: dict[str, Any]) -> str:
    """target_sector_universe_review.md 본문."""
    lines: list[str] = []
    summary = payload.get("summary") or {}
    lines.append("# 산업 종목풀 검토 리포트 (사업 근거 기반)")
    lines.append("")
    lines.append(f"- 생성 시각: {payload.get('generated_at', '')}")
    lines.append(f"- 분류 방식: {payload.get('classification_method', '')}")
    lines.append(f"- 기준일: {payload.get('trading_date', '')}")
    lines.append("")
    lines.append("## 데이터 소스")
    ds = payload.get("data_sources") or {}
    for k, v in ds.items():
        lines.append(f"- {k}: {'사용' if v else '미사용/부족'}")
    lines.append("")
    lines.append("## 산업군별 포함 종목 수")
    lines.append("")
    lines.append("| 산업군 | 포함(included) | 검토필요(needs_review) |")
    lines.append("|--------|----------------|------------------------|")
    for sec in payload.get("sectors") or []:
        sk = sec.get("sector_key", "")
        stocks = sec.get("stocks") or []
        n_review = sum(1 for s in stocks if s.get("review_status") == "needs_review")
        lines.append(
            f"| {sec.get('sector_name', sk)} | {len(stocks)} | {n_review} |"
        )
    lines.append("")
    lines.append("## 기존 키워드 79종 대비")
    lines.append("")
    lines.append(f"- 종목명 키워드 매칭(가격 무관): **{summary.get('old_keyword_matched_count', 0)}**종")
    lines.append(
        f"- 그중 사업 근거 부족으로 **제외·재검토**: **{summary.get('old_keyword_weak_excluded_count', 0)}**종"
    )
    lines.append(
        f"- 사업 근거 **included** 합계: **{summary.get('new_included_count', 0)}**종"
    )
    missed = summary.get("missed_by_keyword_then_included") or []
    lines.append(
        f"- 키워드로는 놓쳤으나 사업 설명으로 **포함 확인**: **{len(missed)}**종"
    )
    if missed:
        lines.append("")
        for m in missed[:15]:
            lines.append(
                f"  - {m.get('name')} / {m.get('ticker')} → {', '.join(m.get('sector_keys') or [])}"
            )
    lines.append("")
    lines.append("## 필수 검토 6종목")
    lines.append("")
    lines.append("| 종목 | 코드 | 산업군 | 검토상태 | 신뢰도 | 사업 요약 |")
    lines.append("|------|------|--------|----------|--------|-----------|")
    for code, info in (summary.get("mandatory_six") or {}).items():
        sk = ", ".join(info.get("sector_keys") or []) or "—"
        lines.append(
            f"| {info.get('name')} | {code} | {sk} | {info.get('review_status')} | "
            f"{info.get('classification_confidence')} | {info.get('business_summary', '')} |"
        )
    lines.append("")
    for sec in payload.get("sectors") or []:
        lines.append(f"## {sec.get('sector_name', '')}")
        lines.append("")
        lines.append(
            "| 종목명 | 코드 | 사업내용 요약 | 포함 이유 | 근거 수준 | 검토 상태 |"
        )
        lines.append(
            "|--------|------|---------------|-----------|-----------|-----------|"
        )
        for s in sec.get("stocks") or []:
            lines.append(
                f"| {s.get('name')} | {s.get('ticker')} | "
                f"{(s.get('business_summary') or '')[:80]} | "
                f"{(s.get('inclusion_reason') or '')[:60]} | "
                f"{s.get('classification_confidence')} / {s.get('evidence_type')} | "
                f"{s.get('review_status')} |"
            )
        lines.append("")
    if payload.get("errors"):
        lines.append("## 오류")
        for e in payload["errors"]:
            lines.append(f"- {e}")
    return "\n".join(lines)
