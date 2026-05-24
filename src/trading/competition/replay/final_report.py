"""REPLAY full-audit final comprehensive report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS, TEAM_META, TEAM_TO_AGENT
from src.trading.competition.replay.benchmark import compute_weighted_benchmark, team_vs_benchmark
from src.trading.competition.replay.firestore_store import replay_report_url, sync_replay_final_report
from src.trading.competition.replay.period import (
    FULL_AUDIT_END,
    FULL_AUDIT_PERIOD_LABEL,
    FULL_AUDIT_SLACK_LABEL,
    FULL_AUDIT_START,
)
from src.trading.competition.runtime import COMPETITION_ROOT

KST = ZoneInfo("Asia/Seoul")
CAMPAIGNS_ROOT = COMPETITION_ROOT / "replay" / "campaigns"
REPLAY_ROOT = COMPETITION_ROOT / "replay"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _month_key(yyyymmdd: str) -> str:
    return f"m{yyyymmdd[:6]}"


def _aggregate_audit_counts(run_ids: list[str]) -> dict[str, int]:
    leakage_fail = 0
    rule_violations = 0
    unverified_evidence = 0

    for rid in run_ids:
        run_dir = REPLAY_ROOT / rid
        manifest = _read_json(run_dir / "manifest.json")
        if manifest.get("leakage_summary") == "FAIL":
            leakage_fail += 1
        rule_violations += int(manifest.get("code_audit_failures") or 0)

        for dec in _read_jsonl(run_dir / "decisions.jsonl"):
            leak = (dec.get("leakage_audit") or {}).get("status")
            if leak == "FAIL":
                leakage_fail += 1
            elif leak in ("UNVERIFIED", "LIMITED"):
                unverified_evidence += 1

        for row in _read_jsonl(run_dir / "audit" / "decisions_audit.jsonl"):
            if not row.get("ok"):
                rule_violations += 1
            for ev in row.get("evidence_issues") or []:
                if "unverified" in str(ev).lower():
                    unverified_evidence += 1

    return {
        "future_data_leakage_count": leakage_fail,
        "rule_violation_count": rule_violations,
        "unverified_evidence_count": unverified_evidence,
    }


def _collect_trades_and_decisions(run_ids: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trades: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for rid in run_ids:
        run_dir = REPLAY_ROOT / rid
        for tr in _read_jsonl(run_dir / "trades.jsonl"):
            tr["replay_run_id"] = rid
            trades.append(tr)
        for dec in _read_jsonl(run_dir / "decisions.jsonl"):
            dec["replay_run_id"] = rid
            decisions.append(dec)
    return trades, decisions


def _best_worst_decisions(
    trades: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    scored: list[dict[str, Any]] = []
    for tr in trades:
        pnl = tr.get("realized_pnl_krw")
        if pnl is None:
            continue
        scored.append(
            {
                "kind": "trade",
                "team_id": tr.get("team_id"),
                "ticker": tr.get("ticker"),
                "name": tr.get("name"),
                "side": tr.get("side"),
                "pnl_krw": int(pnl),
                "replay_run_id": tr.get("replay_run_id"),
            }
        )
    for dec in decisions:
        if str(dec.get("action", "")).upper() not in ("BUY", "ADD_BUY", "SELL"):
            continue
        leak = (dec.get("leakage_audit") or {}).get("status")
        scored.append(
            {
                "kind": "decision",
                "team_id": dec.get("team_id"),
                "ticker": dec.get("ticker"),
                "action": dec.get("action"),
                "reason_label": dec.get("reason_label"),
                "pnl_krw": 0,
                "leakage_status": leak,
                "replay_run_id": dec.get("replay_run_id"),
            }
        )

    if not scored:
        return None, None
    with_pnl = [s for s in scored if s.get("kind") == "trade"]
    if with_pnl:
        best = max(with_pnl, key=lambda x: x["pnl_krw"])
        worst = min(with_pnl, key=lambda x: x["pnl_krw"])
        return best, worst
    return scored[0], scored[-1]


def _sell_decision_evaluation(decisions: list[dict[str, Any]], trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sells = [d for d in decisions if str(d.get("action", "")).upper() == "SELL"]
    sell_trades = [t for t in trades if "sell" in str(t.get("side", "")).lower()]
    out: list[dict[str, Any]] = []
    for dec in sells[:20]:
        tid = dec.get("team_id")
        ticker = dec.get("ticker")
        matched = [
            t
            for t in sell_trades
            if t.get("team_id") == tid and str(t.get("ticker")) == str(ticker)
        ]
        out.append(
            {
                "team_id": tid,
                "ticker": ticker,
                "reason_label": dec.get("reason_label"),
                "filled": bool(matched),
                "realized_pnl_krw": matched[-1].get("realized_pnl_krw") if matched else None,
                "leakage_status": (dec.get("leakage_audit") or {}).get("status"),
            }
        )
    if not out and not sells:
        out.append(
            {
                "summary": "기간 내 SELL 판단 없음 — 보유 종목은 종료일 종가 기준 평가손익으로 반영",
                "filled": False,
            }
        )
    return out


def _monthly_flow_from_accounts(
    run_ids: list[str],
    final_accounts: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rid in run_ids:
        m = _read_json(REPLAY_ROOT / rid / "manifest.json")
        td = str(m.get("trading_date") or "")
        if td:
            by_month[_month_key(td)].append(m)

    flow: dict[str, list[dict[str, Any]]] = {tid: [] for tid in TEAM_IDS}
    for month_key in sorted(by_month.keys()):
        month_manifests = sorted(by_month[month_key], key=lambda x: x.get("trading_date", ""))
        y, mo = int(month_key[1:5]), int(month_key[5:7])
        for tid in TEAM_IDS:
            last = month_manifests[-1]
            acc = (last.get("accounts") or {}).get(tid) or {}
            end = int(acc.get("total_assets_krw") or INITIAL_CASH_KRW)
            ret = round((end - INITIAL_CASH_KRW) / INITIAL_CASH_KRW * 100, 2)
            flow[tid].append(
                {
                    "month_key": month_key,
                    "label": f"{y}년 {mo}월",
                    "end_assets_krw": end,
                    "return_pct": ret,
                    "trading_days": len(month_manifests),
                }
            )

    if not run_ids:
        return flow
    last_manifest = _read_json(REPLAY_ROOT / run_ids[-1] / "manifest.json")
    val_date = str(last_manifest.get("trading_date") or FULL_AUDIT_END)
    mk = _month_key(val_date)
    for tid in TEAM_IDS:
        acc = final_accounts.get(tid) or {}
        end = int(acc.get("total_assets_krw") or INITIAL_CASH_KRW)
        ret = round((end - INITIAL_CASH_KRW) / INITIAL_CASH_KRW * 100, 2)
        months = flow.get(tid) or []
        if months and months[-1].get("month_key") == mk:
            months[-1]["end_assets_krw"] = end
            months[-1]["return_pct"] = ret
            months[-1]["final_mark_to_market"] = True
        elif months:
            y, mo = int(mk[1:5]), int(mk[5:7])
            months.append(
                {
                    "month_key": mk,
                    "label": f"{y}년 {mo}월 (종료 평가)",
                    "end_assets_krw": end,
                    "return_pct": ret,
                    "final_mark_to_market": True,
                }
            )
        flow[tid] = months
    return flow


def _committee_verdicts(last_manifest: dict[str, Any], audit_counts: dict[str, int]) -> dict[str, Any]:
    committee = last_manifest.get("committee") or {}
    per_team: dict[str, str] = {}
    for tid in TEAM_IDS:
        meta = TEAM_META[tid]
        per_team[tid] = (
            f"{meta['display_name']}: REPLAY full_audit 종료 — "
            f"침범 {audit_counts['future_data_leakage_count']}건, "
            f"규칙위반 {audit_counts['rule_violation_count']}건"
        )
    if committee.get("verdict") or committee.get("summary"):
        per_team["_overall"] = str(committee.get("verdict") or committee.get("summary"))
    elif committee.get("skipped"):
        per_team["_overall"] = "AI 감사위원회 미실행(run_audit_ai=false) — 코드·침범 집계만 반영"
    return per_team


def _live_readiness_conclusion(
    audit_counts: dict[str, int],
    leakage_campaign: str,
    benchmark: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if leakage_campaign == "FAIL" or audit_counts["future_data_leakage_count"] > 0:
        blockers.append("미래 데이터 침범 또는 침범 의심 건 존재")
    if audit_counts["rule_violation_count"] > 0:
        blockers.append("규칙 위반 판단 건 존재")
    if audit_counts["unverified_evidence_count"] > 5:
        blockers.append("검증 불가 근거 다수")
    if not benchmark.get("verified"):
        blockers.append("벤치마크 수익률 미검증(지수 OHLCV 조회 실패)")
    blockers.append("거래 비용 모델 미구현(costs_not_implemented) — LIVE 시작 전 P0")

    ready = len(blockers) == 0
    if ready:
        conclusion = "조건부 가능 — full_audit REPLAY 종료·침범·규칙 집계 PASS. LIVE 재개 전 운영 점검·알림 정책 확인 권장."
    else:
        conclusion = "불가 — " + "; ".join(blockers)
    return {"live_ready": ready, "conclusion": conclusion, "blockers": blockers}


def build_replay_final_report(
    campaign_id: str,
    run_ids: list[str],
    final_accounts: dict[str, dict[str, Any]],
    *,
    last_trading_date: str,
    leakage_summary: str = "PASS",
    last_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit_counts = _aggregate_audit_counts(run_ids)
    trades, decisions = _collect_trades_and_decisions(run_ids)
    best, worst = _best_worst_decisions(trades, decisions)
    sell_eval = _sell_decision_evaluation(decisions, trades)
    benchmark = compute_weighted_benchmark()

    teams_ranked: list[dict[str, Any]] = []
    for tid in TEAM_IDS:
        acc = final_accounts.get(tid) or {}
        end = int(acc.get("total_assets_krw") or INITIAL_CASH_KRW)
        ret = round((end - INITIAL_CASH_KRW) / INITIAL_CASH_KRW * 100, 2)
        teams_ranked.append(
            {
                "team_id": tid,
                "agent_key": TEAM_TO_AGENT[tid],
                "display_name": TEAM_META[tid]["display_name"],
                "final_assets_krw": end,
                "cumulative_return_pct": ret,
                "vs_benchmark": team_vs_benchmark(ret, benchmark),
            }
        )
    teams_ranked.sort(key=lambda x: x["final_assets_krw"], reverse=True)
    for i, row in enumerate(teams_ranked, start=1):
        row["rank"] = i

    last_m = last_manifest or {}
    if run_ids and not last_m:
        last_m = _read_json(REPLAY_ROOT / run_ids[-1] / "manifest.json")

    monthly_flow = _monthly_flow_from_accounts(run_ids, final_accounts)
    committee = _committee_verdicts(last_m, audit_counts)
    live = _live_readiness_conclusion(audit_counts, leakage_summary, benchmark)

    report_id = f"rfr_{campaign_id}"
    report = {
        "report_id": report_id,
        "report_type": "final",
        "report_key": "final",
        "campaign_id": campaign_id,
        "label": FULL_AUDIT_SLACK_LABEL,
        "period": {
            "start": FULL_AUDIT_START,
            "end": FULL_AUDIT_END,
            "label": FULL_AUDIT_PERIOD_LABEL,
        },
        "competition_status": "ended",
        "final_valuation_date": last_trading_date,
        "teams": teams_ranked,
        "monthly_flow": monthly_flow,
        "best_decision": best,
        "worst_decision": worst,
        "sell_evaluation": sell_eval,
        "benchmark": benchmark,
        "audit_counts": audit_counts,
        "committee_verdicts": committee,
        "live_readiness": live,
        "leakage_summary": leakage_summary,
        "overall": [
            f"기간 {FULL_AUDIT_PERIOD_LABEL} REPLAY full_audit 종료",
            "거래 비용: costs_not_implemented — 수수료·세금·제비용 미반영 (LIVE P0)",
            f"최종 평가일 {last_trading_date} — 보유종목 강제 매도 없이 종가(또는 검증 가능 가격) 평가",
            f"미래 데이터 침범 {audit_counts['future_data_leakage_count']}건 / "
            f"규칙 위반 {audit_counts['rule_violation_count']}건 / "
            f"검증 불가 근거 {audit_counts['unverified_evidence_count']}건",
            live["conclusion"],
        ],
        "last_replay_run_id": run_ids[-1] if run_ids else None,
        "url": replay_report_url(
            campaign_id=campaign_id,
            report_key="final",
            report_type="final",
            replay_run_id=run_ids[-1] if run_ids else None,
        ),
        "generated_at": datetime.now(KST).isoformat(),
    }
    return report


def save_final_report(campaign_id: str, report: dict[str, Any]) -> dict[str, Any]:
    camp_dir = CAMPAIGNS_ROOT / campaign_id / "reports"
    camp_dir.mkdir(parents=True, exist_ok=True)
    path = camp_dir / "final.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index_path = camp_dir / "index.json"
    index = _read_json(index_path) if index_path.is_file() else {}
    index["final"] = "final"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fs = sync_replay_final_report(report["report_id"], report)
    return {"path": str(path), "firestore": fs}


def load_final_report(campaign_id: str) -> dict[str, Any] | None:
    path = CAMPAIGNS_ROOT / campaign_id / "reports" / "final.json"
    data = _read_json(path)
    return data or None
