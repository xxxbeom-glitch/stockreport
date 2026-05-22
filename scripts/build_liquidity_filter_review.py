# -*- coding: utf-8 -*-
"""현재 candidate_universe 최종 후보 기준 거래대금 임계값 시뮬레이션 (필터 미적용)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.models import SECTOR_GROUPS, SECTOR_LABELS

CANDIDATE_PATH = ROOT / "data" / "mock_trading" / "candidate_universe.json"
OUTPUT_PATH = ROOT / "data" / "mock_trading" / "liquidity_filter_review.md"

THRESHOLDS: list[tuple[str, int]] = [
    ("5억 이상", 500_000_000),
    ("10억 이상", 1_000_000_000),
    ("20억 이상", 2_000_000_000),
    ("30억 이상", 3_000_000_000),
    ("50억 이상", 5_000_000_000),
    ("100억 이상", 10_000_000_000),
]

MANDATORY: list[tuple[str, str]] = [
    ("403870", "HPSP"),
    ("067310", "하나마이크론"),
    ("319660", "피에스케이"),
    ("074600", "원익QnC"),
    ("058610", "에스피지"),
    ("099440", "스맥"),
]

AI_TARGET_MIN = 40
AI_TARGET_MAX = 80
SECTOR_MIN_WARN = 5


def _fmt_won(v: int | float | None) -> str:
    if v is None:
        return "—"
    eok = int(v) / 100_000_000
    if eok >= 100:
        return f"{eok:,.0f}억"
    if eok >= 1:
        return f"{eok:,.1f}억"
    return f"{int(v):,}원"


def _sector_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {sk: 0 for sk in SECTOR_GROUPS}
    for row in rows:
        keys = row.get("sector_keys") or [row.get("sector_group")]
        for sk in keys:
            if sk in counts:
                counts[sk] += 1
    return counts


def _avg_tv(row: dict[str, Any]) -> int | None:
    m = row.get("metrics") or {}
    v = m.get("avg_trading_value_5d")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _mandatory_status(doc: dict[str, Any], pool: list[dict[str, Any]]) -> dict[str, str]:
    in_pool = {str(c["ticker"]).zfill(6): c for c in pool}
    out: dict[str, str] = {}
    exclusion_lists = [
        ("가격 초과", doc.get("excluded_by_price") or []),
        ("위험", doc.get("excluded_by_risk") or []),
        ("시장(KOSPI 등)", doc.get("excluded_by_market") or []),
        ("유동성(현행 5억)", doc.get("excluded_by_liquidity") or []),
        ("조회 실패", doc.get("lookup_failures") or []),
    ]
    excluded_map: dict[str, str] = {}
    for label, items in exclusion_lists:
        for item in items:
            if not isinstance(item, dict):
                continue
            t = str(item.get("ticker") or "").zfill(6)
            reason = str(item.get("reason") or item.get("detail") or label)
            excluded_map[t] = f"{label}: {reason}"

    for code, name in MANDATORY:
        if code in in_pool:
            tv = _avg_tv(in_pool[code])
            out[code] = f"현재 후보 113종 포함 (5일 평균 {_fmt_won(tv)})"
        elif code in excluded_map:
            out[code] = f"현재 후보 풀 제외 — {excluded_map[code]}"
        else:
            out[code] = "현재 후보 113종·제외 목록 모두 없음"
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    doc = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    candidates: list[dict[str, Any]] = list(doc.get("candidates") or [])
    base_n = len(candidates)
    mandatory_base = _mandatory_status(doc, candidates)

    lines: list[str] = []
    lines.append("# 거래대금 기준 시뮬레이션 리포트")
    lines.append("")
    lines.append(f"- 기준 데이터: `{CANDIDATE_PATH.name}`")
    lines.append(f"- 현재 최종 후보(변경 없음): **{base_n}종**")
    lines.append(f"- 시뮬레이션 대상: 위 {base_n}종의 `metrics.avg_trading_value_5d`")
    lines.append(f"- 생성 시각: {doc.get('generated_at', '')}")
    lines.append("")
    lines.append("> 본 리포트는 필터 코드를 바꾸지 않습니다. 임계값별 잔존 수만 비교합니다.")
    lines.append("")

    summary_rows: list[dict[str, Any]] = []

    for label, threshold in THRESHOLDS:
        kept = [c for c in candidates if (_avg_tv(c) or 0) >= threshold]
        excluded_n = base_n - len(kept)
        by_sector = _sector_counts(kept)
        kept_codes = {str(c["ticker"]).zfill(6) for c in kept}

        lines.append(f"## {label} (≥ {_fmt_won(threshold)})")
        lines.append("")
        lines.append(f"1. **남는 전체 종목 수**: {len(kept)}종 (제외 {excluded_n}종)")
        lines.append("")
        lines.append("2. **산업군별 종목 수**")
        lines.append("")
        lines.append("| 산업군 | 종목 수 |")
        lines.append("|--------|--------|")
        for sk in SECTOR_GROUPS:
            name = SECTOR_LABELS.get(sk, sk)
            cnt = by_sector.get(sk, 0)
            warn = " ⚠️" if sk == "industrial_robot_equipment" and cnt < SECTOR_MIN_WARN else ""
            lines.append(f"| {name} | {cnt}{warn} |")
        lines.append("")

        lines.append("3. **제외되는 종목 수**: " + str(excluded_n))
        lines.append("")
        lines.append("4. **필수 확인 6종목**")
        lines.append("")
        lines.append("| 종목 | 코드 | 잔존 여부 |")
        lines.append("|------|------|-----------|")
        for code, name in MANDATORY:
            if code in kept_codes:
                row = next(c for c in kept if str(c["ticker"]).zfill(6) == code)
                status = f"**잔존** ({_fmt_won(_avg_tv(row))})"
            else:
                status = mandatory_base.get(code, "미포함")
                if code in {str(c["ticker"]).zfill(6) for c in candidates}:
                    tv = _avg_tv(next(c for c in candidates if str(c["ticker"]).zfill(6) == code))
                    status = f"이번 기준 제외 (5일 평균 {_fmt_won(tv)})"
            lines.append(f"| {name} | {code} | {status} |")
        lines.append("")

        top10 = sorted(
            kept,
            key=lambda c: (_avg_tv(c) or 0),
            reverse=True,
        )[:10]
        lines.append("5. **거래대금 상위 10종**")
        lines.append("")
        lines.append("| 순위 | 종목 | 코드 | 5일 평균 거래대금 | 현재가 |")
        lines.append("|------|------|------|-----------------|--------|")
        for i, row in enumerate(top10, 1):
            cp = row.get("current_price")
            cp_s = f"{int(cp):,}원" if isinstance(cp, (int, float)) else "—"
            lines.append(
                f"| {i} | {row.get('name')} | {row.get('ticker')} | "
                f"{_fmt_won(_avg_tv(row))} | {cp_s} |"
            )
        lines.append("")

        summary_rows.append(
            {
                "label": label,
                "threshold": threshold,
                "total": len(kept),
                "by_sector": by_sector,
                "in_range": AI_TARGET_MIN <= len(kept) <= AI_TARGET_MAX,
            }
        )

    lines.append("## 기준별 요약")
    lines.append("")
    lines.append("| 거래대금 기준 | 전체 | 반도체 | 전력 | 로봇·장비 | 40~80종 |")
    lines.append("|--------------|------|--------|------|-----------|---------|")
    for row in summary_rows:
        bs = row["by_sector"]
        in_rng = "✓" if row["in_range"] else ""
        robot = bs.get("industrial_robot_equipment", 0)
        robot_note = " ⚠️" if robot < SECTOR_MIN_WARN else ""
        lines.append(
            f"| {row['label']} | {row['total']} | "
            f"{bs.get('ai_semiconductor_material_equipment', 0)} | "
            f"{bs.get('power_technology', 0)} | "
            f"{robot}{robot_note} | {in_rng} |"
        )
    lines.append("")

    in_range = [r for r in summary_rows if r["in_range"]]
    lines.append("## 추천 분석")
    lines.append("")
    if in_range:
        viable = [
            r
            for r in in_range
            if r["by_sector"].get("industrial_robot_equipment", 0) >= SECTOR_MIN_WARN
        ]
        best_count = min(in_range, key=lambda r: abs(r["total"] - 60))
        best_balance = min(
            viable or in_range,
            key=lambda r: (abs(r["total"] - 60), -r["threshold"]),
        )
        lines.append(
            f"- **40~80종 범위 충족 기준**: {', '.join(r['label'] for r in in_range)}"
        )
        lines.append(
            f"- **종목 수만 보면 60종 근접**: **{best_count['label']}** → {best_count['total']}종"
        )
        lines.append(
            f"- **산업군 균형(로봇·장비≥5) 고려 시**: **{best_balance['label']}** → {best_balance['total']}종"
        )
    else:
        below = [r for r in summary_rows if r["total"] < AI_TARGET_MIN]
        above = [r for r in summary_rows if r["total"] > AI_TARGET_MAX]
        if below and above:
            lines.append(
                f"- 40종 미만: {below[-1]['label']}({below[-1]['total']}종) ~ "
                f"80종 초과: {above[0]['label']}({above[0]['total']}종) 사이에서 결정 필요"
            )

    lines.append("- **산업군 편중**")
    for row in summary_rows:
        bs = row["by_sector"]
        total = row["total"] or 1
        robot = bs.get("industrial_robot_equipment", 0)
        semi = bs.get("ai_semiconductor_material_equipment", 0)
        if robot < SECTOR_MIN_WARN:
            lines.append(f"  - {row['label']}: 로봇·장비 **{robot}종** (5종 미만 ⚠️)")
        elif semi / total > 0.75:
            lines.append(
                f"  - {row['label']}: 반도체 비중 **{semi}/{total}** (75% 초과, 편중 주의)"
            )
        else:
            lines.append(
                f"  - {row['label']}: 반도체 {semi} / 전력 {bs.get('power_technology', 0)} / "
                f"로봇·장비 {robot}"
            )

    lines.append("")
    lines.append("## 다음 단계 권고(코드 미적용)")
    lines.append("")
    if in_range:
        viable = [
            r
            for r in in_range
            if r["by_sector"].get("industrial_robot_equipment", 0) >= SECTOR_MIN_WARN
        ]
        pool = viable or in_range
        rec = min(pool, key=lambda r: (abs(r["total"] - 60), -r["threshold"]))
        alt = min(
            [r for r in in_range if r["label"] != rec["label"]],
            key=lambda r: abs(r["total"] - 60),
            default=None,
        )
        lines.append(
            f"1. **권장 적용 기준**: **{rec['label']}** "
            f"(예상 {rec['total']}종 — 반도체 {rec['by_sector'].get('ai_semiconductor_material_equipment', 0)} / "
            f"전력 {rec['by_sector'].get('power_technology', 0)} / "
            f"로봇·장비 {rec['by_sector'].get('industrial_robot_equipment', 0)})"
        )
        if alt:
            lines.append(
                f"2. **대안**: {alt['label']} ({alt['total']}종) — "
                "종목 수는 비슷하나 산업군 균형이 다름 (상세는 위 표 참고)."
            )
        lines.append(
            "3. 현행 5억 원 하한은 유지하고, AI 입력 직전 **추가** 거래대금 컷으로만 축소하는 방식을 권장합니다."
        )
        if any(
            r["by_sector"].get("industrial_robot_equipment", 0) < SECTOR_MIN_WARN
            for r in in_range
        ):
            lines.append(
                "4. **50억 이상**은 전체 58종으로 적정하나 로봇·장비 4종(⚠️) — "
                "산업군 균형을 우선하면 **30억 이상(76종, 로봇 7)** 또는 **20억 이상(80종, 로봇 8)**이 낫습니다."
            )
    else:
        lines.append(
            "1. 단일 임계값만으로 40~80종이 안 맞으면, **30억 + 산업군별 상한** 등 "
            "복합 기준을 다음 단계에서 검토하세요."
        )
    lines.append(
        "2. 하나마이크론(투자경고)·피에스케이·에스피지(가격)는 "
        "거래대금과 무관하게 현재 풀에 없으므로, 별도 예외 규칙이 필요하면 논의하세요."
    )

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({base_n} base candidates)")
    for row in summary_rows:
        print(f"  {row['label']}: {row['total']} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
