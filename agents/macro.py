"""Macro strategist agent (Gemini + fallback)."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json
import traceback
from typing import Any

import config
from utils.helpers import safe_json_parse
from utils.retry import retry


def _fallback(indicators: dict[str, Any], sector_temp: dict[str, Any]) -> dict[str, Any]:
    favorable = [k for k, v in sector_temp.items() if v.get("flow") == "유입"][:3]
    unfavorable = [k for k, v in sector_temp.items() if v.get("flow") == "유출"][:3]
    phase = "중립"
    reason = "섹터 유입과 유출이 혼재되어 방향성이 뚜렷하지 않습니다."
    if favorable and not unfavorable:
        phase, reason = "위험선호", "자금 유입 섹터가 우세해 위험자산 선호가 유지되고 있습니다."
    elif unfavorable and not favorable:
        phase, reason = "위험회피", "자금 유출 섹터가 우세해 보수적 대응이 필요합니다."
    return {
        "market_phase": phase,
        "market_phase_reason": reason,
        "dollar_impact": str(indicators.get("dollar_index", "N/A")),
        "rate_impact": str(indicators.get("us10y", "N/A")),
        "sector_rotation": {"flowing_in": favorable, "flowing_out": unfavorable},
        "favorable_sectors": favorable,
        "unfavorable_sectors": unfavorable,
        "verdicts": {},
        "summary": f"현재 시장 국면은 {phase}입니다.",
        "meta": {"mode": "fallback"},
    }


@retry(max_attempts=2, delay_sec=1.0)
def analyze_macro(
    indicators: dict[str, Any], sector_temp: dict[str, Any], news: str, logger: Any = None
) -> dict[str, Any]:
    """Analyze macro regime with Gemini JSON response."""
    if not config.GEMINI_API_KEY:
        if logger:
            logger.log(config.GEMINI_PRO_MODEL, "macro", input_tokens=0, output_tokens=0)
        result = _fallback(indicators, sector_temp)
        result["summary"] = "GEMINI_API_KEY 미설정으로 폴백 사용"
        return result

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_PRO_MODEL)
        prompt = f"""
너는 거시경제/매크로 전략가야.
아래 데이터를 분석해서 한국어 JSON만 반환해.

[선행지표]
{json.dumps(indicators, ensure_ascii=False)}

[섹터 온도]
{json.dumps(sector_temp, ensure_ascii=False)}

[주요 뉴스]
{news[:1500]}

스키마:
{{
  "market_phase":"위험선호/위험회피/중립",
  "market_phase_reason":"설명",
  "dollar_impact":"설명",
  "rate_impact":"설명",
  "sector_rotation":{{"flowing_in":["섹터"],"flowing_out":["섹터"]}},
  "favorable_sectors":["섹터"],
  "unfavorable_sectors":["섹터"],
  "verdicts":{{"종목명":{{"vote":"매수","reason":["이유1","이유2"]}}}},
  "summary":"한 줄 요약"
}}
"""
        response = model.generate_content(prompt)
        if logger and hasattr(response, "usage_metadata") and response.usage_metadata:
            logger.log(
                model=config.GEMINI_PRO_MODEL,
                agent="macro",
                input_tokens=int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0),
            )
        text = getattr(response, "text", "") or ""
        parsed = safe_json_parse(text)
        if parsed:
            parsed.setdefault("meta", {"mode": "gemini"})
            return parsed
        print("[WARN] macro: Gemini responded but JSON parse failed")
        print(f"[WARN] macro raw head: {text[:500]!r}")
    except Exception:
        print("[ERROR] macro Gemini call failed:")
        print(traceback.format_exc())

    if logger:
        logger.log(config.GEMINI_PRO_MODEL, "macro", input_tokens=0, output_tokens=0)
    result = _fallback(indicators, sector_temp)
    result["meta"] = {"mode": "fallback-on-error"}
    return result
