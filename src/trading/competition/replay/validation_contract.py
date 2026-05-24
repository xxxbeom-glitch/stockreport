"""Campaign validation status vs SYSTEM_CONTRACT — formal performance gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.trading.competition.runtime import COMPETITION_ROOT

DOCS_REPLAY_ROOT = Path(__file__).resolve().parents[4] / "docs" / "replay-data"
CAMPAIGNS_DOCS = DOCS_REPLAY_ROOT / "campaigns"

STATUS_FORMAL = "formal_strategy_performance"
STATUS_DEVELOPMENT_ONLY = "development_validation_only"

CANONICAL_IN_PROGRESS_CAMPAIGN = "month_20260102_20260130_1b51cb"

# Until verified per trading_date, these block formal_strategy_performance for the campaign.
DEFAULT_UNVERIFIED_ITEMS: list[dict[str, str]] = [
    {
        "id": "C_SUPPLY_HISTORICAL",
        "team": "C",
        "description": "기관·외국인 수급 데이터가 리플레이 거래일 당시 기준으로 제공되는지 미검증",
        "contract_ref": "D-05",
    },
    {
        "id": "UNIVERSE_AS_OF_DATE",
        "team": "ALL",
        "description": "리플레이 종목 마스터·가격·거래대금·위험상태가 해당 거래일 시점 기준인지 미검증 (static master/KIS enrich 경로)",
        "contract_ref": "D-02",
    },
    {
        "id": "RISK_AS_OF_DATE",
        "team": "ALL",
        "description": "관리종목·거래정지·위험상태 필터가 해당 거래일 시점 기준인지 미검증",
        "contract_ref": "D-02",
    },
]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def validation_status_path(campaign_id: str) -> Path:
    return CAMPAIGNS_DOCS / campaign_id / "validation_status.json"


def load_campaign_validation_status(campaign_id: str) -> dict[str, Any]:
    """Load published validation record; fall back to in-code defaults for known campaigns."""
    path = validation_status_path(campaign_id)
    if path.is_file():
        data = _read_json(path)
        data.setdefault("campaignId", campaign_id)
        return data

    if campaign_id == CANONICAL_IN_PROGRESS_CAMPAIGN:
        return default_development_validation_record(campaign_id)

    return {
        "campaignId": campaign_id,
        "performanceStatus": STATUS_FORMAL,
        "formalStrategyPerformanceAllowed": True,
        "dashboardLabel": "REPLAY 정식 성과",
        "unverifiedItems": [],
        "notes": "No validation_status.json; treated as formal unless configured.",
    }


def default_development_validation_record(campaign_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaignId": campaign_id,
        "performanceStatus": STATUS_DEVELOPMENT_ONLY,
        "formalStrategyPerformanceAllowed": False,
        "dashboardLabel": "개발 검증 데이터 (정식 전략 성과 아님)",
        "contractDocument": "docs/competition/SYSTEM_CONTRACT.md",
        "unverifiedItems": list(DEFAULT_UNVERIFIED_ITEMS),
        "notes": (
            "Pipeline/infrastructure validation only until unverified items are cleared. "
            "Do not use returns or rankings as formal strategy performance."
        ),
    }


def save_campaign_validation_status(campaign_id: str, record: dict[str, Any]) -> Path:
    path = validation_status_path(campaign_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def merge_validation_into_meta(meta: dict[str, Any], campaign_id: str) -> dict[str, Any]:
    """Attach validation fields for Pages meta.json and dashboard payloads."""
    v = load_campaign_validation_status(campaign_id)
    out = dict(meta)
    out["performanceStatus"] = v.get("performanceStatus")
    out["formalStrategyPerformanceAllowed"] = bool(v.get("formalStrategyPerformanceAllowed"))
    out["validationDashboardLabel"] = v.get("dashboardLabel")
    out["unverifiedItemIds"] = [item.get("id") for item in (v.get("unverifiedItems") or []) if item.get("id")]
    return out


def is_formal_strategy_performance(campaign_id: str) -> bool:
    return bool(load_campaign_validation_status(campaign_id).get("formalStrategyPerformanceAllowed"))


def local_validation_mirror_path(campaign_id: str) -> Path:
    return COMPETITION_ROOT / "replay" / "campaigns" / campaign_id / "validation_status.json"
