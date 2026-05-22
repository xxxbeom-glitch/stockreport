# -*- coding: utf-8 -*-
"""사업 설명·검증 데이터 기반 산업군 분류 (종목명 단독 최종 포함 금지)."""

from __future__ import annotations

import re
from typing import Any, Literal

from agents.mock_trading.models import SECTOR_GROUPS, SECTOR_KEYWORDS

SectorKey = Literal[
    "ai_semiconductor_material_equipment",
    "power_technology",
    "industrial_robot_equipment",
]

Confidence = Literal["high", "medium", "needs_review"]
ReviewStatus = Literal["included", "needs_review", "excluded"]
EvidenceType = Literal[
    "business_description",
    "disclosure",
    "official_company_info",
    "existing_verified_data",
]

# 종목명 키워드만으로는 최종 포함 불가
NAME_ONLY_WEAK: frozenset[str] = frozenset(
    {
        "소재",
        "장비",
        "산업",
        "설비",
        "전기",
        "솔루션",
        "에너지",
        "정밀",
        "공정",
        "발전",
        "모터",
        "자동화",
        "디스플레이",
        "PCB",
        "스크린",
        "칩",
        "에피",
    }
)

# Tier A: 사업 핵심이 명확한 구체 구문 (1개만으로 included 가능)
TIER_A_PHRASES: dict[SectorKey, tuple[str, ...]] = {
    "ai_semiconductor_material_equipment": (
        "반도체 장비",
        "반도체 제조 장비",
        "반도체용",
        "웨이퍼",
        "식각",
        "증착",
        "세정",
        "어닐링",
        "HBM",
        "후공정",
        "전공정",
        "노광",
        "PR 스트립",
        "PR스트립",
        "CMP",
        "펠리클",
        "쿼츠웨어",
        "쿼츠",
        "건식",
        "진공펌프",
        "메모리 테스트",
        "테스트 핸들러",
        "테스트 장비",
        "CVD",
        "PVD",
        "플라즈마",
        "오버레이",
        "포토레지스트",
        "감광액",
        "스크러버",
        "Scrubber",
        "패키징 장비",
        "다이본딩",
        "본딩와이어",
        "칩머운트",
        "웨이퍼링",
        "백그라인드",
        "반도체 검사",
        "반도체 패키징",
        "반도체 후공정",
        "반도체 전공정",
    ),
    "power_technology": (
        "변압기",
        "전력망",
        "송배전",
        "송전",
        "배전",
        "HVDC",
        "GIS",
        "차단기",
        "계전",
        "스위치기어",
        "중전기",
        "전력변환",
        "전력 제어",
        "전력제어",
        "원자력",
        "원전",
        "SMR",
        "소형모듈원자로",
        "발전설비",
        "전력기기",
        "전력 케이블",
        "전력케이블",
        "배전반",
        "집광채",
    ),
    "industrial_robot_equipment": (
        "산업용 로봇",
        "협동로봇",
        "감속기",
        "서보모터",
        "정밀 모터",
        "정밀모터",
        "CNC",
        "공작기계",
        "공정 자동화",
        "공정자동화",
        "자동화 설비",
        "로봇 부품",
        "로봇부품",
        "직교로봇",
        "스카라",
    ),
}

# Tier B: 보조 신호 — 동일 산업에서 2개 이상 또는 Tier A와 조합
TIER_B_PHRASES: dict[SectorKey, tuple[str, ...]] = {
    "ai_semiconductor_material_equipment": (
        "반도체",
        "패키징",
        "테스트",
        "핸들러",
        "파운드리",
    ),
    "power_technology": (
        "터빈",
        "발전기",
        "전동기 제어",
        "전력 반도체",
    ),
    "industrial_robot_equipment": (
        "로봇",
        "FA ",
        "머신비전",
        "산업 자동화",
        "액추에이터",
    ),
}

# 사업 텍스트에 있으면 해당 산업에서 제외(오분류 방지)
EXCLUDE_PHRASES: dict[SectorKey, tuple[str, ...]] = {
    "ai_semiconductor_material_equipment": (
        "태양광",
        "신재생에너지",
        "2차전지",
        "배터리",
        "바이오",
        "의약",
        "게임",
        "엔터테인",
        "유통",
        "건설",
        "조선",
        "선박",
        "LNG선",
        "보냉재",
        "피팅",
        "밸브",
        "위성",
        "방산",
        "드론",
    ),
    "power_technology": (
        "태양광",
        "풍력",
        "2차전지",
        "배터리 셀",
        "바이오",
        "게임",
        "유통",
        "화장품",
        "조선",
        "선박",
        "반도체 설계",
        "팹리스",
        "Fabless",
        "fabless",
        "IP ",
        "설계 전문",
    ),
    "industrial_robot_equipment": (
        "태양광",
        "2차전지",
        "바이오",
        "게임",
        "조선",
        "LNG",
        "보냉재",
        "피팅",
        "크레인",
        "위성",
        "방산",
        "반도체",
        "웨이퍼",
    ),
}

# kr_watchlist sector_key → target sector_keys
WATCHLIST_SECTOR_MAP: dict[str, list[SectorKey]] = {
    "semiconductor_subdev": ["ai_semiconductor_material_equipment"],
    "aerospace_defense": [],  # 이번 3대 산업 풀 대상 아님
    "shipbuilding_robotics": ["industrial_robot_equipment"],  # business 재검증
}

MANDATORY_REVIEW_TICKERS: frozenset[str] = frozenset(
    {
        "403870",  # HPSP
        "067310",  # 하나마이크론
        "319660",  # 피에스케이
        "074600",  # 원익QnC
        "058610",  # 에스피지
        "099440",  # 스맥
    }
)

# 조선·피팅 등 watchlist 내 비로봇 (사업문구로 제외)
SHIPBUILDING_NON_ROBOT_TICKERS: frozenset[str] = frozenset(
    {
        "014620",
        "013030",
        "014940",
        "017960",
        "033500",
        "023160",
    }
)


def _name_keyword_hints(name: str) -> list[str]:
    hints: list[str] = []
    upper = name.upper()
    for group in SECTOR_GROUPS:
        for kw in SECTOR_KEYWORDS.get(group, ()):
            if kw.upper() in upper or kw in name:
                hints.append(kw)
    return sorted(set(hints))


def _phrase_hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    if not text:
        return []
    hits: list[str] = []
    lower = text.lower()
    for p in phrases:
        token = p.strip().lower()
        if not token:
            continue
        if token in lower or token in text:
            hits.append(p.strip())
    return hits


def _has_exclude(text: str, sector: SectorKey) -> bool:
    return bool(_phrase_hits(text, EXCLUDE_PHRASES.get(sector, ())))


def _sector_match(combined: str, sector: SectorKey) -> tuple[list[str], Confidence | None]:
    """(matched_phrases, confidence) — 매칭 없으면 ([], None)."""
    if _has_exclude(combined, sector):
        return [], None
    tier_a = _phrase_hits(combined, TIER_A_PHRASES[sector])
    tier_b = _phrase_hits(combined, TIER_B_PHRASES[sector])
    if tier_a:
        return tier_a + tier_b, "high"
    if len(tier_b) >= 2:
        return tier_b, "medium"
    if len(tier_b) == 1:
        return tier_b, "needs_review"
    return [], None


def classify_from_business_text(
    business_text: str,
    *,
    name: str = "",
    krx_industry: str = "",
) -> dict[str, Any]:
    """사업 설명(및 보조 KRX 업종)만으로 산업군 판정."""
    combined = " ".join(
        x for x in (business_text.strip(), f"KRX업종:{krx_industry}" if krx_industry else "") if x
    )
    sector_hits: dict[SectorKey, list[str]] = {}
    sector_conf: dict[SectorKey, Confidence] = {}

    for sector in SECTOR_GROUPS:
        sk: SectorKey = sector  # type: ignore[assignment]
        hits, conf = _sector_match(combined, sk)
        if hits and conf:
            sector_hits[sk] = hits
            sector_conf[sk] = conf

    name_hints = _name_keyword_hints(name)
    name_only_weak = name_hints and all(h in NAME_ONLY_WEAK for h in name_hints)

    sector_keys = list(sector_hits.keys())
    if not sector_keys:
        if name_only_weak and business_text:
            return {
                "sector_keys": [],
                "classification_confidence": "needs_review",
                "review_status": "needs_review",
                "inclusion_reason": "종목명 약한 키워드만 매칭, 사업 설명에 강한 산업 신호 없음",
                "evidence_summary": f"discovery_hint={name_hints}",
            }
        return {
            "sector_keys": [],
            "classification_confidence": "needs_review",
            "review_status": "excluded",
            "inclusion_reason": "사업 설명 기준 해당 산업 신호 없음",
            "evidence_summary": "",
        }

    confidences = [sector_conf[sk] for sk in sector_keys]
    if len(sector_keys) > 1:
        overall: Confidence = "needs_review"
        review_status: ReviewStatus = "needs_review"
    elif "needs_review" in confidences:
        overall = "needs_review"
        review_status = "needs_review"
    elif all(c == "high" for c in confidences):
        overall = "high"
        review_status = "included"
    else:
        overall = "medium"
        review_status = "included"

    reasons = []
    for sk, hits in sector_hits.items():
        reasons.append(f"{sk}: {', '.join(hits[:4])} ({sector_conf[sk]})")

    return {
        "sector_keys": sector_keys,
        "classification_confidence": overall,
        "review_status": review_status,
        "inclusion_reason": "; ".join(reasons),
        "evidence_summary": combined[:400],
    }


def classify_watchlist_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """data/kr_watchlist.json 검증 데이터."""
    wl_sector = str(entry.get("sector_key") or "")
    ticker = str(entry.get("ticker") or "").zfill(6)
    business = str(entry.get("business") or "").strip()
    name = str(entry.get("name") or "")

    if wl_sector == "aerospace_defense":
        return {
            "sector_keys": [],
            "classification_confidence": "high",
            "review_status": "excluded",
            "inclusion_reason": "우주항공·방산은 이번 3대 산업 풀 범위 외",
            "evidence_type": "existing_verified_data",
            "evidence_summary": business,
            "discovery_hint_keywords": _name_keyword_hints(name),
        }

    if wl_sector == "shipbuilding_robotics" and ticker in SHIPBUILDING_NON_ROBOT_TICKERS:
        biz = classify_from_business_text(business, name=name)
        if not biz["sector_keys"]:
            return {
                **biz,
                "evidence_type": "existing_verified_data",
                "discovery_hint_keywords": _name_keyword_hints(name),
                "review_status": "excluded",
                "inclusion_reason": "조선·플랜트 부품 중심, 로봇·자동화 장비 아님",
            }

    mapped = WATCHLIST_SECTOR_MAP.get(wl_sector, [])
    biz = classify_from_business_text(business, name=name)
    sector_keys = list(biz["sector_keys"])
    if mapped and not sector_keys:
        sector_keys = [sk for sk in mapped if sk in SECTOR_GROUPS]  # type: ignore[arg-type]

    if wl_sector == "semiconductor_subdev" and business:
        sector_keys = ["ai_semiconductor_material_equipment"]
        confidence: Confidence = "high"
        review_status: ReviewStatus = "included"
    elif sector_keys:
        confidence = biz["classification_confidence"]  # type: ignore[assignment]
        review_status = biz["review_status"]  # type: ignore[assignment]
    else:
        confidence = "needs_review"
        review_status = "needs_review"

    if ticker in MANDATORY_REVIEW_TICKERS and not sector_keys:
        sector_keys = list(mapped) if mapped else []
        review_status = "needs_review"
        confidence = "needs_review"

    return {
        "sector_keys": sector_keys,
        "classification_confidence": confidence,
        "review_status": review_status,
        "inclusion_reason": str(entry.get("selection_reason") or biz.get("inclusion_reason") or ""),
        "evidence_type": "existing_verified_data",
        "evidence_summary": business or str(biz.get("evidence_summary") or ""),
        "discovery_hint_keywords": _name_keyword_hints(name),
        "business_summary": business,
    }
