# -*- coding: utf-8 -*-
"""candidate_universe.json → 사람용 검토 리포트 (AI 호출 없음)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.models import SECTOR_GROUPS, SECTOR_KEYWORDS, SECTOR_LABELS
from agents.mock_trading.universe_builder import classify_sector_groups

UNIVERSE_PATH = ROOT / "data" / "mock_trading" / "candidate_universe.json"
REPORT_PATH = ROOT / "data" / "mock_trading" / "candidate_review.md"

# 종목명만으로 오분류 가능성이 큰 키워드
WEAK_KEYWORDS: frozenset[str] = frozenset(
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
        "디스플레이",
        "PCB",
        "발전",
        "모터",
        "자동화",
        "스크린",
    }
)

USER_SECTOR_DESCRIPTIONS: dict[str, str] = {
    "ai_semiconductor_material_equipment": (
        "AI 반도체 소재·부품·장비 (반도체 장비, 소재, 테스트, 패키징, 후공정, 식각, 증착, 세정, 쿼츠웨어 등)"
    ),
    "power_technology": (
        "전력기술 (전력기기, 전력망, 변압기, 전력제어, 원전/SMR 관련 장비 등)"
    ),
    "industrial_robot_equipment": (
        "산업·로봇 장비 (공정 자동화, 산업용 장비, 로봇 부품, 정밀 모터, 감속기 등)"
    ),
}


def _matched_keywords_detail(name: str) -> dict[str, list[str]]:
    """산업군별 실제 매칭된 키워드."""
    upper = name.upper()
    out: dict[str, list[str]] = {}
    for group in SECTOR_GROUPS:
        hits: list[str] = []
        for kw in SECTOR_KEYWORDS.get(group, ()):
            if kw.upper() in upper or kw in name:
                hits.append(kw)
        if hits:
            out[group] = hits
    return out


def _fmt_bool(v: Any) -> str:
    if v is True:
        return "통과"
    if v is False:
        return "미통과"
    return "미확인"


def _assess_row(row: dict[str, Any]) -> dict[str, Any]:
    name = str(row.get("name") or "")
    assigned = str(row.get("sector_group") or "")
    all_groups = classify_sector_groups(name)
    kw_detail = _matched_keywords_detail(name)
    assigned_kws = kw_detail.get(assigned, [])
    all_kws = [kw for kws in kw_detail.values() for kw in kws]

    labels = [SECTOR_LABELS.get(g, g) for g in all_groups] if all_groups else []
    if assigned and assigned not in all_groups:
        all_groups = list(dict.fromkeys([assigned] + all_groups))
        labels = [SECTOR_LABELS.get(g, g) for g in all_groups]

    weak_only = bool(all_kws) and all(kw in WEAK_KEYWORDS for kw in all_kws)
    assigned_weak_only = bool(assigned_kws) and all(
        kw in WEAK_KEYWORDS for kw in assigned_kws
    )

    flags: list[str] = []
    if weak_only or assigned_weak_only:
        flags.append("근거 약함")
    if len(all_groups) > 1:
        flags.append("복수 산업군")
    if not assigned_kws:
        flags.append("검토 필요")
    elif assigned_weak_only and len(all_groups) == 1:
        flags.append("검토 필요")

    if not flags and assigned_kws:
        clarity = "명확"
    elif "근거 약함" in flags:
        clarity = "근거 약함"
    else:
        clarity = "검토 필요"

    filters = row.get("filters") or {}
    return {
        "name": name,
        "ticker": row.get("ticker"),
        "price": row.get("current_price"),
        "assigned_group": assigned,
        "assigned_label": SECTOR_LABELS.get(assigned, assigned),
        "all_group_labels": labels,
        "matched_keywords": kw_detail,
        "match_reason": ", ".join(
            f"{SECTOR_LABELS.get(g, g)}:{','.join(kws)}"
            for g, kws in kw_detail.items()
        ),
        "clarity": clarity,
        "review_flags": flags,
        "market_status": row.get("market_check_status") or "미확인",
        "price_pass": filters.get("price_under_59000"),
        "tradable": filters.get("tradable"),
        "risk_check": filters.get("risk_check_status") or "미확인",
        "liquidity": filters.get("liquidity_pass"),
        "business_summary": row.get("business_summary") or "",
    }


def _build_report(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    summary = payload.get("universe_summary") or {}
    lines: list[str] = []

    lines.append("# 모의투자 후보군 검토 리포트")
    lines.append("")
    lines.append(f"- week_id: {payload.get('week_id', '')}")
    lines.append(f"- 생성 시각: {payload.get('generated_at', '')}")
    lines.append(f"- 데이터 모드: {payload.get('mode', '')}")
    lines.append(f"- 가격 출처: {summary.get('price_source_mode', 'pykrx_bulk')}")
    lines.append("")
    lines.append("## 요약")
    lines.append("")
    lines.append(f"| 항목 | 건수 |")
    lines.append(f"|------|------|")
    lines.append(f"| 전체 코스닥 조회 | {summary.get('kosdaq_total_checked', '—')} |")
    lines.append(f"| 관심 산업 키워드 매칭 | {summary.get('industry_matched', '—')} |")
    lines.append(f"| 59,000원 이하 (가격 필터 통과) | {summary.get('price_under_59000', '—')} |")
    lines.append(f"| 최종 후보 | {summary.get('final_candidate_count', len(rows))} |")
    lines.append("")

    clarity_counts = Counter(r["clarity"] for r in rows)
    sector_counts = Counter(r["assigned_group"] for r in rows)

    lines.append("### 분류 검증 집계")
    lines.append("")
    lines.append(f"- 산업 연관성 **명확**: {clarity_counts.get('명확', 0)}종")
    lines.append(f"- **검토 필요**: {clarity_counts.get('검토 필요', 0)}종")
    lines.append(f"- **근거 약함** (단순 키워드): {clarity_counts.get('근거 약함', 0)}종")
    lines.append("")
    lines.append("### 산업군별 후보 (배정 기준)")
    lines.append("")
    for g in SECTOR_GROUPS:
        lines.append(
            f"- {USER_SECTOR_DESCRIPTIONS[g]}: **{sector_counts.get(g, 0)}**종"
        )
    lines.append("")

    lines.append("## 관심 산업군 정의")
    lines.append("")
    for i, (g, desc) in enumerate(USER_SECTOR_DESCRIPTIONS.items(), 1):
        lines.append(f"{i}. **{SECTOR_LABELS[g]}** — {desc}")
    lines.append("")

    lines.append("## 종목별 상세")
    lines.append("")

    by_sector: dict[str, list[dict[str, Any]]] = {g: [] for g in SECTOR_GROUPS}
    for r in rows:
        by_sector.setdefault(r["assigned_group"], []).append(r)

    for g in SECTOR_GROUPS:
        group_rows = sorted(by_sector.get(g, []), key=lambda x: x["name"])
        if not group_rows:
            continue
        lines.append(f"### {SECTOR_LABELS[g]} ({len(group_rows)}종)")
        lines.append("")
        lines.append(
            "| 종목명 | 코드 | 현재가 | 배정 산업군 | 복수 라벨 | 매칭 키워드 | "
            "연관성 | 가격 | 시장 | 거래/위험 | 유동성 | 검토 |"
        )
        lines.append(
            "|--------|------|--------|------------|----------|-------------|"
            "--------|------|------|-----------|------|------|"
        )
        for r in group_rows:
            multi = (
                ", ".join(r["all_group_labels"])
                if len(r["all_group_labels"]) > 1
                else "—"
            )
            flags = ", ".join(r["review_flags"]) if r["review_flags"] else "—"
            price = (
                f"{int(r['price']):,}원" if r.get("price") is not None else "미확인"
            )
            lines.append(
                f"| {r['name']} | {r['ticker']} | {price} | {r['assigned_label']} | "
                f"{multi} | {r['match_reason'] or '—'} | {r['clarity']} | "
                f"{_fmt_bool(r['price_pass'])} | {r['market_status']} | "
                f"{_fmt_bool(r['tradable'])}/{r['risk_check']} | "
                f"{_fmt_bool(r['liquidity'])} | {flags} |"
            )
        lines.append("")

    lines.append("## AI 실행 전 권고")
    lines.append("")
    review_n = clarity_counts.get("검토 필요", 0) + clarity_counts.get("근거 약함", 0)
    if review_n == 0:
        verdict = (
            "현재 79종 후보군은 **산업 분류·가격 조건(dry-run/pykrx 기준)** 으로 "
            "**그대로 AI 추천 입력에 사용 가능**해 보입니다. "
            "다만 아래 가격 재검증은 필수입니다."
        )
    elif review_n <= 15:
        verdict = (
            f"**{review_n}종**은 종목명 키워드만으로 분류되어 **분류 보완을 권장**합니다. "
            "명확 종목만으로 AI를 돌리거나, 키워드·제외 규칙을 조정한 뒤 "
            "`run_weekly_recommendation_agents.py --dry-run`으로 후보군을 재생성하세요."
        )
    else:
        verdict = (
            f"**{review_n}종**이 검토/근거 약함 상태입니다. "
            "**AI 실행 전 분류 규칙 보완** (키워드 강화·약한 키워드 제외·수동 화이트리스트)을 "
            "권장합니다."
        )
    lines.append(verdict)
    lines.append("")
    lines.append(
        "> **중요:** 이 리포트의 현재가·가격 통과 여부는 "
        "`candidate_universe.json` dry-run 시점의 **pykrx 일괄 시세** 기준입니다. "
        "**실제 AI 추천(`--live-ai`) 직전**에는 반드시 "
        "`python scripts/run_weekly_recommendation_agents.py --use-kis-prices` 등으로 "
        "**KIS 현재가 기준 59,000원 이하** 조건을 다시 검사하세요."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not UNIVERSE_PATH.is_file():
        print(f"실패: {UNIVERSE_PATH} 없음")
        return 1

    payload = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") or []
    rows = [_assess_row(c) for c in candidates]
    report = _build_report(payload, rows)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"저장: {REPORT_PATH}")
    print(f" 후보 {len(rows)}종 분석 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
