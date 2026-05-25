"""Five-trading-day performance report (fact-based, no mock prose)."""

from __future__ import annotations

from typing import Any

from src.trading.simple_replay.constants import AGENT_UI, TEAM_IDS


def build_performance_report(
    *,
    manifest: dict[str, Any],
    decisions: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    team_totals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pos_by = {p["team_id"]: p for p in positions}
    dec_by = {d["team_id"]: d for d in decisions}

    agents = []
    for tid in TEAM_IDS:
        ui = AGENT_UI[tid]
        totals = team_totals[tid]
        pos = pos_by.get(tid)
        dec = dec_by.get(tid)
        stock = "-"
        if pos:
            stock = f"{pos.get('name')} ({pos.get('final_return_pct'):+.2f}%)"
        agents.append(
            {
                "key": ui["agent_key"],
                "startAsset": 500_000,
                "endAsset": totals["total_asset"],
                "returnPct": totals["cumulative_return_pct"],
                "contributionLabel": dec.get("reason_label") if dec else "SKIP",
                "contributionStock": stock,
                "contributionPnl": pos.get("final_unrealized_pnl", 0) if pos else 0,
                "tierEval": ui["strategy_label"],
                "selfEval": (dec.get("reason_summary") or "")[:200] if dec else "추천 없음",
                "nextWeek": "SIMPLE_REPLAY 5거래일 관찰 종료",
            }
        )

    ranked = sorted(positions, key=lambda p: p.get("final_return_pct", 0), reverse=True)
    best = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None

    overall: list[str] = []
    for tid in TEAM_IDS:
        t = team_totals[tid]
        ui = AGENT_UI[tid]
        overall.append(
            f"{ui['display_name']}({ui['strategy_label']}): "
            f"최종자산 {t['total_asset']:,}원, 수익률 {t['cumulative_return_pct']:+.2f}%"
        )

    if best:
        overall.append(
            f"최고 수익 추천: {best.get('name')} {best.get('final_return_pct'):+.2f}% "
            f"({AGENT_UI[best['team_id']]['display_name']})"
        )
    if worst and worst is not best:
        overall.append(
            f"최대 손실 추천: {worst.get('name')} {worst.get('final_return_pct'):+.2f}% "
            f"— {worst.get('reason_label')}"
        )

    skips = [tid for tid in TEAM_IDS if dec_by.get(tid, {}).get("action") != "BUY"]
    if skips:
        overall.append(
            "추천 없음 팀: "
            + ", ".join(AGENT_UI[t]["display_name"] for t in skips)
            + " — 후보 부족 또는 팩트 근거 미달"
        )

    winner = max(TEAM_IDS, key=lambda t: team_totals[t]["cumulative_return_pct"])
    overall.append(
        f"이번 구간 가장 유효한 전략: {AGENT_UI[winner]['strategy_label']} "
        f"({AGENT_UI[winner]['display_name']})"
    )

    dd = manifest.get("decision_date", "")
    label = f"{dd[4:6]}.{dd[6:8]} 추천 · 5거래일 검증" if len(dd) == 8 else "5거래일 검증"

    return {
        "label": label,
        "period": (
            f"기준일 {dd} → 매수 {manifest.get('buy_date')} → "
            f"평가 {', '.join(manifest.get('evaluation_dates') or [])}"
        ),
        "agents": agents,
        "overall": overall,
        "best_pick": best,
        "worst_pick": worst,
    }
