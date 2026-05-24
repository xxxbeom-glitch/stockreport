"""Weekly report generation and dashboard binding (spec §13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.trading.competition.constants import TEAM_IDS, TEAM_META, TEAM_TO_AGENT
from src.trading.competition.execution.market_session import is_weekly_report_window
from src.trading.competition.models import now_kst_iso
from src.trading.competition.storage.accounts import load_all_accounts
from src.trading.competition.storage.base import ROOT, load_json_file, save_json_file
from src.trading.competition.storage.journal import append_notification, load_decisions, load_trades

KST = ZoneInfo("Asia/Seoul")
REPORTS_DIR = ROOT / "data" / "competition" / "weekly_reports"
LATEST_PATH = REPORTS_DIR / "latest.json"


def should_generate_weekly_report(at: datetime | None = None) -> bool:
    """Friday after last allowed trading session (20:00 KST+)."""
    return is_weekly_report_window(at)


def _week_key(at: datetime | None = None) -> str:
    now = at.astimezone(KST) if at else datetime.now(KST)
    iso = now.isocalendar()
    return f"w{iso.week}"


def build_weekly_report(week_label: str | None = None, *, period: str = "", force: bool = False) -> dict[str, Any] | None:
    if not force and not should_generate_weekly_report():
        return None

    accounts = load_all_accounts()
    trades = load_trades()
    decisions = load_decisions()
    key = week_label or _week_key()

    agents = []
    for tid in TEAM_IDS:
        acc = accounts.get(tid)
        meta = TEAM_META[tid]
        initial = acc.initial_cash_krw if acc else INITIAL_CASH_KRW
        end = acc.total_assets_krw if acc else initial
        ret = round((end - initial) / initial * 100, 2) if initial else 0
        team_trades = [t for t in trades if t.get("team_id") == tid]
        agents.append(
            {
                "key": TEAM_TO_AGENT[tid],
                "startAsset": initial,
                "endAsset": end,
                "returnPct": ret,
                "contributionLabel": "주간 체결",
                "contributionStock": team_trades[-1].get("name", "-") if team_trades else "-",
                "contributionPnl": team_trades[-1].get("realized_pnl_krw") if team_trades else 0,
                "tierEval": f"판단 {len([d for d in decisions if d.get('team_id')==tid])}회",
                "selfEval": f"팀 {tid} 주간 운용 — 체결 {len(team_trades)}건",
                "nextWeek": "세션별 재판단 유지",
            }
        )

    now = datetime.now(KST)
    report = {
        "report_id": f"wkr_{uuid.uuid4().hex[:10]}",
        "label": f"{now.month}월 {now.isocalendar().week % 5 or 1}주차",
        "period": period or now.strftime("%m.%d") + " 주간",
        "agents": agents,
        "overall": [
            f"주간 AI 판단 {len(decisions)}회, 체결 {len(trades)}건",
            "C/D 검증 파트너 영향은 decision/review 로그 기준 분석",
        ],
        "generated_at": now_kst_iso(),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    save_json_file(REPORTS_DIR / f"{key}.json", report)
    save_json_file(LATEST_PATH, report)

    append_notification(
        {
            "notification_id": f"ntf_{uuid.uuid4().hex[:10]}",
            "category": "report",
            "title": "주간 리포트 생성 완료",
            "sub": report["label"],
            "read": False,
            "created_at": now_kst_iso(),
        }
    )
    return report


def load_weekly_reports_for_dashboard() -> dict[str, Any]:
    """Format for dashboard WEEKLY_REPORTS (wN keys)."""
    out: dict[str, Any] = {}
    if not REPORTS_DIR.is_dir():
        return out
    for p in sorted(REPORTS_DIR.glob("w*.json")):
        if p.name == "latest.json":
            continue
        data = load_json_file(p, {})
        if data:
            out[p.stem] = data
    if not out and LATEST_PATH.is_file():
        data = load_json_file(LATEST_PATH, {})
        if data:
            out[_week_key()] = data
    return out
