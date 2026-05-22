# -*- coding: utf-8 -*-
"""AI 입력 후보 분리 + 뉴스·공시·수급 컨텍스트 수집 (추천 AI/Grok 호출 없음)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.ai_candidate_builder import run_build_pipeline

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("AI 입력 후보·컨텍스트 빌드 시작 (AI/Grok 호출 없음)")
    result = run_build_pipeline()
    print("")
    print(f"기준 후보: {result['base_count']}종")
    print(f"AI 입력 후보: {result['ai_input_count']}종")
    print("산업군별:", result["sector_counts"])
    st = result["stats"]
    print(f"뉴스 — ok:{st.get('news_ok')} empty:{st.get('news_empty')} "
          f"fail:{st.get('news_fail')} skip:{st.get('news_skip')}")
    print(f"공시 — ok:{st.get('disclosure_ok')} empty:{st.get('disclosure_empty')} "
          f"fail:{st.get('disclosure_fail')} skip:{st.get('disclosure_skip')}")
    print(f"수급(외국인) — ok:{st.get('flow_ok')} empty:{st.get('flow_empty')} "
          f"fail:{st.get('flow_fail')}")
    for name, path in result["paths"].items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
