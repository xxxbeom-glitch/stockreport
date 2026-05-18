"""Supply and demand analyst agent (Grok + fallback)."""

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
    sector_flow = market_data.get("sector_flow", [])
    top_inflow: list[dict[str, str]] = []
    volume_alerts: list[dict[str, Any]] = []
    for stock in discovered[:8]:
        ratio = stock.get("volume_ratio")
        if ratio is None:
            continue
        ratio_text = f"{float(ratio):.2f}x"
        name = str(stock.get("name", stock.get("ticker", "UNKNOWN")))
        top_inflow.append({"name": name, "reason": "거래량 집중", "volume_x": ratio_text})
        volume_alerts.append({"name": name, "volume_x": ratio_text, "change": "N/A", "is_up": True})

    inflow = [s.get("sector", "UNKNOWN") for s in sector_flow[:5] if s.get("flow") == "유입"]
    outflow = [s.get("sector", "UNKNOWN") for s in sector_flow[:5] if s.get("flow") == "유출"]
    return {
        "top_inflow_stocks": top_inflow,
        "volume_alerts": volume_alerts,
        "sector_flow": {"유입": inflow, "유출": outflow},
        "verdicts": {},
        "summary": "수급 폴백 분석 결과",
        "meta": {"mode": "fallback"},
    }


@retry(max_attempts=2, delay_sec=1.0)
def analyze_supply_demand(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """Analyze supply-demand signals with Grok JSON response."""
    if not config.GROK_API_KEY:
        if logger:
            logger.log(config.GROK_MODEL, "supply_demand", input_tokens=0, output_tokens=0)
        result = _fallback(market_data)
        result["summary"] = "GROK_API_KEY 미설정으로 폴백 사용"
        return result

    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=config.GROK_API_KEY, base_url=config.GROK_BASE_URL)
        prompt = f"""
너는 주식 수급 분석 전문가야.
아래 데이터를 보고 JSON만 반환해.

[시장 데이터]
{json.dumps(market_data, ensure_ascii=False)[:5000]}

반드시 아래 스키마:
{{
  "top_inflow_stocks": [{{"name":"종목명","reason":"이유","volume_x":"2.1배"}}],
  "volume_alerts": [{{"name":"종목명","volume_x":"2.9배","change":"+3.1%","is_up":true}}],
  "sector_flow": {{"유입":["섹터"],"유출":["섹터"]}},
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
                agent="supply_demand",
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
        logger.log(config.GROK_MODEL, "supply_demand", input_tokens=0, output_tokens=0)
    result = _fallback(market_data)
    result["meta"] = {"mode": "fallback-on-error"}
    return result
