"""REPLAY weekly/monthly reports (isolated from LIVE weekly reports)."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS, TEAM_META, TEAM_TO_AGENT
from src.trading.competition.replay.firestore_store import (
    replay_report_url,
    sync_replay_monthly_report,
    sync_replay_weekly_report,
)
from src.trading.competition.runtime import COMPETITION_ROOT

KST = ZoneInfo("Asia/Seoul")
CAMPAIGNS_ROOT = COMPETITION_ROOT / "replay" / "campaigns"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _week_key_from_date(yyyymmdd: str) -> str:
    dt = datetime.strptime(yyyymmdd, "%Y%m%d").replace(tzinfo=KST)
    iso = dt.isocalendar()
    return f"w{iso.week}"


def _month_key_from_date(yyyymmdd: str) -> str:
    return f"m{yyyymmdd[:6]}"


def _load_run_manifests(run_ids: list[str]) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for rid in run_ids:
        p = COMPETITION_ROOT / "replay" / rid / "manifest.json"
        m = _read_json(p)
        if m:
            manifests.append(m)
    return manifests


def build_replay_weekly_reports(
    campaign_id: str,
    run_ids: list[str],
    *,
    leakage_summary: str = "PASS",
) -> list[dict[str, Any]]:
    manifests = _load_run_manifests(run_ids)
    by_week: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in manifests:
        td = str(m.get("trading_date") or "")
        if td:
            by_week[_week_key_from_date(td)].append(m)

    reports: list[dict[str, Any]] = []
    for week_key, week_manifests in sorted(by_week.items()):
        week_manifests.sort(key=lambda x: x.get("trading_date", ""))
        agents = []
        for tid in TEAM_IDS:
            meta = TEAM_META[tid]
            last = week_manifests[-1]
            acc = (last.get("accounts") or {}).get(tid) or {}
            initial = INITIAL_CASH_KRW
            end = int(acc.get("total_assets_krw") or initial)
            ret = round((end - initial) / initial * 100, 2) if initial else 0
            trades = []
            for wm in week_manifests:
                run_dir = COMPETITION_ROOT / "replay" / wm["replay_run_id"]
                trades_path = run_dir / "trades.jsonl"
                if trades_path.is_file():
                    for line in trades_path.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            tr = json.loads(line)
                            if tr.get("team_id") == tid:
                                trades.append(tr)
            agents.append(
                {
                    "key": TEAM_TO_AGENT[tid],
                    "startAsset": initial,
                    "endAsset": end,
                    "returnPct": ret,
                    "contributionLabel": "주간 체결",
                    "contributionStock": trades[-1].get("name", "-") if trades else "-",
                    "contributionPnl": trades[-1].get("realized_pnl_krw", 0) if trades else 0,
                    "tierEval": f"REPLAY {len(week_manifests)}거래일",
                    "selfEval": f"팀 {tid} REPLAY 주간 — 체결 {len(trades)}건",
                    "nextWeek": "REPLAY 검증 계속",
                }
            )
        first_td = week_manifests[0].get("trading_date", "")
        dt = datetime.strptime(str(first_td), "%Y%m%d") if first_td else datetime.now(KST)
        report_id = f"rwr_{campaign_id}_{week_key}"
        report = {
            "report_id": report_id,
            "week_key": week_key,
            "campaign_id": campaign_id,
            "label": f"{dt.month}월 {dt.isocalendar().week % 5 or 1}주차",
            "period": f"REPLAY {week_manifests[0].get('trading_date')}–{week_manifests[-1].get('trading_date')}",
            "agents": agents,
            "overall": [
                f"REPLAY 주간 — 거래일 {len(week_manifests)}일",
                f"미래 데이터 침범: {leakage_summary}",
                "LIVE 성과에 반영되지 않음",
            ],
            "audit": {"leakage_summary": leakage_summary},
            "last_replay_run_id": week_manifests[-1].get("replay_run_id"),
            "url": replay_report_url(
                campaign_id=campaign_id,
                report_key=week_key,
                report_type="weekly",
                replay_run_id=week_manifests[-1].get("replay_run_id"),
            ),
            "generated_at": datetime.now(KST).isoformat(),
        }
        reports.append(report)
    return reports


def build_replay_monthly_reports(
    campaign_id: str,
    run_ids: list[str],
    *,
    leakage_summary: str = "PASS",
) -> list[dict[str, Any]]:
    manifests = _load_run_manifests(run_ids)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in manifests:
        td = str(m.get("trading_date") or "")
        if td:
            by_month[_month_key_from_date(td)].append(m)

    reports: list[dict[str, Any]] = []
    for month_key, month_manifests in sorted(by_month.items()):
        month_manifests.sort(key=lambda x: x.get("trading_date", ""))
        agents = []
        for tid in TEAM_IDS:
            last = month_manifests[-1]
            acc = (last.get("accounts") or {}).get(tid) or {}
            initial = INITIAL_CASH_KRW
            end = int(acc.get("total_assets_krw") or initial)
            ret = round((end - initial) / initial * 100, 2) if initial else 0
            agents.append(
                {
                    "key": TEAM_TO_AGENT[tid],
                    "startAsset": initial,
                    "endAsset": end,
                    "returnPct": ret,
                    "contributionLabel": "월간 성과",
                    "contributionStock": "-",
                    "contributionPnl": end - initial,
                    "tierEval": f"REPLAY {len(month_manifests)}거래일",
                    "selfEval": f"팀 {tid} REPLAY 월간 집계",
                    "nextWeek": "LIVE 시작 전 감사 재확인",
                }
            )
        y, m = int(month_key[1:5]), int(month_key[5:7])
        report_id = f"rmr_{campaign_id}_{month_key}"
        report = {
            "report_id": report_id,
            "month_key": month_key,
            "campaign_id": campaign_id,
            "label": f"{y}년 {m}월",
            "period": f"REPLAY {month_manifests[0].get('trading_date')}–{month_manifests[-1].get('trading_date')}",
            "agents": agents,
            "overall": [
                f"REPLAY 월간 — 거래일 {len(month_manifests)}일",
                f"미래 데이터 누적: {leakage_summary}",
                "LIVE 시작 가능 여부는 감사·평가위원회 및 full replay 결과 참조",
            ],
            "audit": {"leakage_summary": leakage_summary},
            "last_replay_run_id": month_manifests[-1].get("replay_run_id"),
            "url": replay_report_url(
                campaign_id=campaign_id,
                report_key=month_key,
                report_type="monthly",
                replay_run_id=month_manifests[-1].get("replay_run_id"),
            ),
            "generated_at": datetime.now(KST).isoformat(),
        }
        reports.append(report)
    return reports


def save_campaign_reports(
    campaign_id: str,
    weekly: list[dict[str, Any]],
    monthly: list[dict[str, Any]],
) -> dict[str, Any]:
    camp_dir = CAMPAIGNS_ROOT / campaign_id / "reports"
    camp_dir.mkdir(parents=True, exist_ok=True)
    fs_weekly: list[dict[str, Any]] = []
    fs_monthly: list[dict[str, Any]] = []

    for rep in weekly:
        wk = rep["week_key"]
        path = camp_dir / f"weekly_{wk}.json"
        path.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fs_weekly.append(sync_replay_weekly_report(rep["report_id"], rep))

    for rep in monthly:
        mk = rep["month_key"]
        path = camp_dir / f"monthly_{mk}.json"
        path.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fs_monthly.append(sync_replay_monthly_report(rep["report_id"], rep))

    index = {"weekly": [r["week_key"] for r in weekly], "monthly": [r["month_key"] for r in monthly]}
    (camp_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"weekly_firestore": fs_weekly, "monthly_firestore": fs_monthly}


def load_campaign_final_report(campaign_id: str) -> dict[str, Any] | None:
    from src.trading.competition.replay.final_report import load_final_report

    return load_final_report(campaign_id)


def load_campaign_reports(campaign_id: str) -> dict[str, Any]:
    camp_dir = CAMPAIGNS_ROOT / campaign_id / "reports"
    weekly: dict[str, Any] = {}
    monthly: dict[str, Any] = {}
    final_report: dict[str, Any] | None = None
    final_path = camp_dir / "final.json"
    if final_path.is_file():
        final_report = _read_json(final_path)

    if not camp_dir.is_dir():
        return {"weeklyReports": weekly, "monthlyReports": monthly, "finalReport": final_report}
    for p in camp_dir.glob("weekly_*.json"):
        data = _read_json(p)
        if data:
            weekly[data.get("week_key") or p.stem.replace("weekly_", "")] = data
    for p in camp_dir.glob("monthly_*.json"):
        data = _read_json(p)
        if data:
            monthly[data.get("month_key") or p.stem.replace("monthly_", "")] = data
    return {"weeklyReports": weekly, "monthlyReports": monthly, "finalReport": final_report}
