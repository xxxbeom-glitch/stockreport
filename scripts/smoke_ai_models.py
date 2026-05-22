#!/usr/bin/env python3
"""AI 모델 연결 smoke test — 실패 시 하위 모델로 대체하지 않음."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.ai.model_config import log_model_banner, model_status  # noqa: E402
from utils.safe_stdio import safe_print  # noqa: E402


def main() -> int:
    log_model_banner(emit=safe_print)
    status = model_status()
    ok = True
    for w in status["forbidden_warnings"]:
        safe_print(f"[FAIL] {w}")
        ok = False

    from agents.kr_intraday_slack.llm_client import call_primary_json, is_primary_configured

    if is_primary_configured():
        parsed, err = call_primary_json(
            'JSON만: {"ping":"ok"}',
            agent="smoke_deepseek",
        )
        if parsed:
            safe_print("[OK] DeepSeek")
        else:
            safe_print(f"[FAIL] DeepSeek: {err}")
            ok = False
    else:
        safe_print("[SKIP] DeepSeek — API key 없음")

    import config

    if config.GEMINI_API_KEY:
        from agents.gemini_client import generate_gemini_json
        from agents.ai.model_config import GEMINI_MODEL_ID

        parsed = generate_gemini_json(
            'JSON만: {"ping":"ok"}',
            agent="smoke_gemini",
            model=GEMINI_MODEL_ID,
        )
        if parsed:
            safe_print("[OK] Gemini")
        else:
            safe_print("[FAIL] Gemini — 호출/파싱 실패 (구현 보류)")
            ok = False
    else:
        safe_print("[SKIP] Gemini — API key 없음")

    if config.GROK_API_KEY:
        from agents.grok_client import grok_with_web_and_x_search
        from agents.ai.model_config import GROK_MODEL_ID

        text, meta = grok_with_web_and_x_search(
            "Respond JSON: {\"ping\":\"ok\"}",
            agent="smoke_grok",
            model=GROK_MODEL_ID,
            max_output_tokens=200,
        )
        if text:
            safe_print(
                f"[OK] Grok web_search_used={meta.get('web_search_used')} "
                f"x_search_used={meta.get('x_search_used')}"
            )
        else:
            safe_print(f"[FAIL] Grok: {meta.get('error')}")
            ok = False
    else:
        safe_print("[SKIP] Grok — API key 없음")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
