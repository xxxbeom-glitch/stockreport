# -*- coding: utf-8 -*-
"""ai_candidate_context_compact.json → 추천 에이전트 입력."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.mock_trading.models import SECTOR_LABELS

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPACT_PATH = ROOT / "data" / "mock_trading" / "ai_candidate_context_compact.json"
DEFAULT_AI_INPUT_PATH = ROOT / "data" / "mock_trading" / "ai_input_candidates.json"

_LABEL_TO_SECTOR_KEY = {label: key for key, label in SECTOR_LABELS.items()}


def _sector_key_from_label(label: str) -> str:
    s = str(label or "").strip()
    if s in _LABEL_TO_SECTOR_KEY:
        return _LABEL_TO_SECTOR_KEY[s]
    for key, lbl in SECTOR_LABELS.items():
        if lbl.split("·")[0] in s or s in lbl:
            return key
    return "ai_semiconductor_material_equipment"


def compact_row_to_agent_universe(row: dict[str, Any]) -> dict[str, Any]:
    """compact 1행 → recommendation_agents 입력 형식."""
    sector_label = str(row.get("sector") or "")
    sector_key = _sector_key_from_label(sector_label)
    news_ctx = [
        {"title": t, "source": "naver_search_news"}
        for t in (row.get("top_news_titles") or [])[:2]
        if t
    ]
    disc_ctx = [
        {"report_nm": t, "title": t}
        for t in (row.get("top_disclosure_titles") or [])[:2]
        if t
    ]
    return {
        "ticker": str(row.get("ticker") or "").zfill(6),
        "name": row.get("name"),
        "sector_group": sector_key,
        "sector_keys": [sector_key],
        "business_summary": row.get("business_summary"),
        "current_price": row.get("current_price"),
        "metrics": {
            "return_5d_pct": row.get("return_5d_pct"),
            "return_10d_pct": row.get("return_10d_pct"),
            "avg_trading_value_5d": row.get("avg_trading_value_5d"),
            "volume_change": None,
            "foreign_flow": row.get("foreign_flow"),
            "institution_flow": row.get("institution_flow"),
        },
        "news_context": news_ctx,
        "disclosure_context": disc_ctx,
        "warnings": {
            "investment_caution": bool(row.get("investment_caution")),
            "risk_notes": list(row.get("risk_notes") or []),
        },
        "missing_data_note": "기관 수급 미수집 — institution_flow 사용·추정 금지",
    }


def load_compact_universe(
    compact_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    p = compact_path or DEFAULT_COMPACT_PATH
    if not p.is_file():
        return [], {}, f"파일 없음: {p}"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [], {}, f"JSON 로드 실패: {type(exc).__name__}"

    rows = [compact_row_to_agent_universe(r) for r in doc.get("candidates") or [] if isinstance(r, dict)]
    meta = {
        "source_file": str(p.name),
        "candidate_count": len(rows),
        "selection_rule": doc.get("selection_rule"),
        "generated_at": doc.get("generated_at"),
    }
    return rows, meta, None


def load_universe_map_from_ai_input(
    ai_input_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    p = ai_input_path or DEFAULT_AI_INPUT_PATH
    if not p.is_file():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {
        str(c.get("ticker", "")).zfill(6): c
        for c in doc.get("candidates") or []
        if isinstance(c, dict)
    }
