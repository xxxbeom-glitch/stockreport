# -*- coding: utf-8 -*-
"""기존 merged/weekly JSON에 AI 쉬운 해설 적용 (추천 에이전트 재실행 없음)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.plain_language_editor import run_plain_language_editor
from agents.mock_trading.trading_web_sync import MERGED_PATH, WEEKLY_PATH, build_trading_data
from agents.mock_trading.weekly_recommendations_store import save_weekly_from_local_files
from data.api_env import ensure_env_loaded

MOCK_DIR = ROOT / "data" / "mock_trading"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ensure_env_loaded()

    if not MERGED_PATH.is_file():
        print(f"실패: {MERGED_PATH} 없음")
        return 1

    merged = json.loads(MERGED_PATH.read_text(encoding="utf-8"))
    weekly = (
        json.loads(WEEKLY_PATH.read_text(encoding="utf-8"))
        if WEEKLY_PATH.is_file()
        else {}
    )

    print(f"week_id={merged.get('week_id')} cards={len(merged.get('merged_cards') or [])}")
    print("AI 쉬운 해설 생성 중...")

    result = run_plain_language_editor(merged, weekly)
    meta = result.get("plain_language_editor") or {}

    MERGED_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    build_trading_data()
    fb = save_weekly_from_local_files(str(result.get("week_id") or ""))

    n = len(result.get("merged_cards") or [])
    ok_fields = sum(
        1
        for c in result.get("merged_cards") or []
        if c.get("plainReason") and c.get("plainRisk") and c.get("viewGuide")
    )

    print(f"plain 필드: {ok_fields}/{n}")
    print(f"model={meta.get('model_id')} ok={meta.get('ok')} gemini={meta.get('gemini_cards')} fallback={meta.get('fallback_cards')}")
    if meta.get("error"):
        print(f"meta_error={meta.get('error')}")
    print(f"trading_data: {MOCK_DIR / 'trading_data.json'}")
    print(f"Firebase: {fb.get('persist_backend')} ({'OK' if fb.get('ok') else fb.get('error')})")

    sample = (result.get("merged_cards") or [{}])[0]
    if sample:
        print(f"샘플 {sample.get('name')}: {str(sample.get('plainReason', ''))[:70]}...")

    return 0 if ok_fields == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
