"""Momentum analyst agent (Grok + fallback)."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json
from typing import Any

import config
from utils.helpers import safe_json_parse
from utils.retry import retry


def _fallback(market_data: dict[str, Any]) -> dict[str, Any]:
    discovered = market_data.get("discovered_stocks", [])
    strong_momentum: list[dict[str, str]] = []
    overbought_warning: list[dict[str, str]] = []
    for stock in discovered[:10]:
        ratio = float(stock.get("volume_ratio") or 0.0)
        name = str(stock.get("name", stock.get("ticker", "UNKNOWN")))
        if ratio >= 3.0:
            strong_momentum.append({"name": name, "position_52w": "N/A", "trend": "거래량 모멘텀 강함"})
        elif ratio >= 2.0:
            overbought_warning.append({"name": name, "position_52w": "N/A", "reason": "단기 과열 주의"})
    return {
        "strong_momentum": strong_momentum,
        "overbought_warning": overbought_warning,
        "top_theme": "Volume-led rotation",
        "verdicts": {},
        "summary": f"{len(strong_momentum)}개 강세, {len(overbought_warning)}개 과열 경고",
        "meta": {"mode": "fallback"},
    }


@retry(max_attempts=2, delay_sec=1.0)
def analyze_momentum(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """Analyze momentum signals with Grok JSON response."""
    if not config.GROK_API_KEY:
        if logger:
            logger.log(config.GROK_MODEL, "momentum", input_tokens=0, output_tokens=0)
        result = _fallback(market_data)
        result["summary"] = "GROK_API_KEY 미설정으로 폴백 사용"
        return result

    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=config.GROK_API_KEY, base_url=config.GROK_BASE_URL)
        prompt = f"""
너는 모멘텀 트레이딩 전문가야.
아래 데이터를 분석해서 JSON만 반환해.

[시장 데이터]
{json.dumps(market_data, ensure_ascii=False)[:5000]}

스키마:
{{
  "strong_momentum": [{{"name":"종목명","position_52w":"76%","trend":"강한 상승"}}],
  "overbought_warning": [{{"name":"종목명","position_52w":"94%","reason":"고점 근접"}}],
  "top_theme": "테마명",
  "verdicts": {{"종목명":{{"vote":"매수","reason":["이유1","이유2"]}}}},
  "summary": "한 줄 요약"
}}
"""
        res = client.chat.completions.create(
            model=config.GROK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1800,
            response_format={"type": "json_object"},
        )
        if logger and getattr(res, "usage", None):
            logger.log(
                model=config.GROK_MODEL,
                agent="momentum",
                input_tokens=int(getattr(res.usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(res.usage, "completion_tokens", 0) or 0),
            )
        content = (res.choices[0].message.content or "").strip()
        parsed = safe_json_parse(content)
        if parsed:
            parsed.setdefault("meta", {"mode": "grok"})
            return parsed
    except Exception:
        pass

    if logger:
        logger.log(config.GROK_MODEL, "momentum", input_tokens=0, output_tokens=0)
    result = _fallback(market_data)
    result["meta"] = {"mode": "fallback-on-error"}
    return result
