"""Fundamental analyst agent (Gemini + fallback)."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import re
import json
from typing import Any

import config
from utils.helpers import safe_json_parse
from utils.retry import retry


def _fallback_fundamental(market_data: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic fallback when Gemini is unavailable."""
    discovered = market_data.get("discovered_stocks", [])
    valuation: dict[str, dict[str, str]] = {}
    earnings_trend: dict[str, str] = {}
    guidance_quality: dict[str, str] = {}
    target_price: dict[str, dict[str, str]] = {}

    for stock in discovered[:5]:
        name = str(stock.get("name", stock.get("ticker", "UNKNOWN")))
        valuation[name] = {
            "per": "N/A",
            "per_vs_industry": "Insufficient valuation data in pipeline",
            "verdict": "Hold until additional statements are fetched",
        }
        earnings_trend[name] = "unknown"
        guidance_quality[name] = "unknown"
        target_price[name] = {"target": "N/A", "upside": "N/A"}

    return {
        "valuation": valuation,
        "earnings_trend": earnings_trend,
        "guidance_quality": guidance_quality,
        "target_price": target_price,
        "verdicts": {},
        "summary": "Fundamental metrics are limited; rely on risk-managed position sizing.",
        "meta": {"mode": "fallback-no-llm"},
    }


@retry(max_attempts=2, delay_sec=1.0)
def analyze_fundamental(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """
    Analyze basic fundamental perspective.

    Current data pipeline does not include full financial statements,
    so this function returns a conservative placeholder structure.
    """
    if not config.GEMINI_API_KEY:
        result = _fallback_fundamental(market_data)
        result["summary"] = "GEMINI_API_KEY missing; returned fallback fundamental analysis."
        if logger:
            logger.log(config.GEMINI_PRO_MODEL, "fundamental", input_tokens=0, output_tokens=0)
        return result

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_PRO_MODEL)
        prompt = f"""
너는 주식 펀더멘털 분석 전문가야.
아래 시장 데이터를 바탕으로 초보 투자자가 이해하기 쉬운 분석을 해줘.
설명 없이 JSON만 반환해.

[시장 데이터]
{json.dumps(market_data, ensure_ascii=False)[:5000]}

필수 스키마:
{{
  "valuation": {{
    "종목명": {{
      "per": "32.4배",
      "per_vs_industry": "업종 평균 28배보다 높음",
      "verdict": "고평가지만 성장이 정당화"
    }}
  }},
  "earnings_trend": {{"종목명":"고성장"}},
  "guidance_quality": {{"종목명":"상향"}},
  "target_price": {{"종목명":{{"target":"210,000원","upside":"+15%"}}}},
  "verdicts": {{"종목명":{{"vote":"매수","reason":["이유1","이유2"]}}}},
  "summary": "한 줄 요약"
}}
"""
        response = model.generate_content(prompt)

        if logger and hasattr(response, "usage_metadata") and response.usage_metadata:
            logger.log(
                model=config.GEMINI_PRO_MODEL,
                agent="fundamental",
                input_tokens=int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0),
            )

        text = getattr(response, "text", "") or ""
        text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
        parsed = safe_json_parse(text)
        if parsed:
            parsed.setdefault("meta", {})
            if isinstance(parsed["meta"], dict):
                parsed["meta"]["mode"] = "gemini"
            return parsed
    except Exception:
        pass

    result = _fallback_fundamental(market_data)
    result["meta"] = {"mode": "fallback-on-error"}
    if logger:
        logger.log(config.GEMINI_PRO_MODEL, "fundamental", input_tokens=0, output_tokens=0)
    return result
