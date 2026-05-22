# -*- coding: utf-8 -*-
"""2026-W21 등 기존 추천 JSON에 plainReason/plainRisk/viewGuide 생성(AI 재호출 없음)."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.plain_language import enrich_merged_card
from agents.mock_trading.trading_web_sync import MERGED_PATH, WEEKLY_PATH, build_trading_data
from agents.mock_trading.weekly_recommendations_store import save_weekly_from_local_files

MOCK_DIR = ROOT / "data" / "mock_trading"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _aggregate_by_ticker(weekly: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    reasons: dict[str, list[str]] = defaultdict(list)
    risks: dict[str, list[str]] = defaultdict(list)
    for agent in weekly.get("agents") or []:
        for rec in agent.get("recommendations") or []:
            ticker = str(rec.get("ticker", "")).zfill(6)
            if not ticker:
                continue
            for r in rec.get("reasons") or []:
                if r and r not in reasons[ticker]:
                    reasons[ticker].append(str(r))
            for rf in rec.get("risk_factors") or []:
                if rf and rf not in risks[ticker]:
                    risks[ticker].append(str(rf))
    return reasons, risks


def _enrich_weekly_agents(weekly: dict[str, Any]) -> None:
    """에이전트별 추천에도 plain 필드 부여(내부 원문 reasons/risk_factors 유지)."""
    from agents.mock_trading.plain_language import build_plain_copy

    for agent in weekly.get("agents") or []:
        for rec in agent.get("recommendations") or []:
            if not isinstance(rec, dict):
                continue
            name = str(rec.get("name") or "")
            plain = build_plain_copy(
                name=name,
                reason_lines=list(rec.get("reasons") or []),
                risk_lines=list(rec.get("risk_factors") or []),
                grok_validation=None,
            )
            rec.update(plain)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not MERGED_PATH.is_file() or not WEEKLY_PATH.is_file():
        print("실패: merged/weekly JSON 없음")
        return 1

    merged = _load(MERGED_PATH)
    weekly = _load(WEEKLY_PATH)
    week_id = str(merged.get("week_id") or weekly.get("week_id") or "")
    reason_map, risk_map = _aggregate_by_ticker(weekly)

    enriched_cards: list[dict[str, Any]] = []
    for card in merged.get("merged_cards") or []:
        ticker = str(card.get("ticker", "")).zfill(6)
        enriched_cards.append(
            enrich_merged_card(
                card,
                extra_reasons=reason_map.get(ticker),
                extra_risks=risk_map.get(ticker),
                force=True,
            )
        )

    merged["merged_cards"] = enriched_cards
    MERGED_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    _enrich_weekly_agents(weekly)
    WEEKLY_PATH.write_text(
        json.dumps(weekly, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    build_trading_data()
    fb = save_weekly_from_local_files(week_id or None)

    print(f"week_id={week_id}")
    print(f"plain 필드 반영: {len(enriched_cards)}종")
    print(f"trading_data 갱신: {MOCK_DIR / 'trading_data.json'}")
    print(
        f"Firebase 저장: {fb.get('persist_backend')} "
        f"({'OK' if fb.get('ok') else fb.get('error', 'FAIL')})"
    )
    if enriched_cards:
        sample = enriched_cards[0]
        print(f"샘플({sample.get('name')}): plainReason={str(sample.get('plainReason'))[:60]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
