"""Risk manager agent (Gemini + fallback)."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json
import traceback
from typing import Any

import config
from utils.helpers import safe_json_parse
from utils.retry import retry


def _fallback(market_data: dict[str, Any]) -> dict[str, Any]:
    discovered = market_data.get("discovered_stocks", [])
    overbought_warnings: list[dict[str, str]] = []
    stop_loss: dict[str, str] = {}
    for stock in discovered[:10]:
        name = str(stock.get("name", stock.get("ticker", "UNKNOWN")))
        ratio = float(stock.get("volume_ratio") or 0.0)
        if ratio >= 3.0:
            overbought_warnings.append(
                {"name": name, "position_52w": "N/A", "warning": "단기 급등으로 변동성 경고"}
            )
        stop_loss[name] = "-8% 하락 시 재검토"
    risk_level = "보통" if overbought_warnings else "낮음"
    return {
        "overbought_warnings": overbought_warnings,
        "hidden_risks": ["데이터 공백 리스크", "유동성 급변 리스크"],
        "stop_loss": stop_loss,
        "portfolio_risk": risk_level,
        "do_not": "과도한 추격매수 금지",
        "verdicts": {},
        "summary": f"포트폴리오 위험도는 {risk_level} 수준입니다.",
        "meta": {"mode": "fallback"},
    }


@retry(max_attempts=2, delay_sec=1.0)
def analyze_risk(
    all_opinions: dict[str, Any], market_data: dict[str, Any], logger: Any = None
) -> dict[str, Any]:
    """Aggregate risks with Gemini JSON response."""
    if not config.GEMINI_API_KEY:
        if logger:
            logger.log(config.GEMINI_PRO_MODEL, "risk", input_tokens=0, output_tokens=0)
        result = _fallback(market_data)
        result["summary"] = "GEMINI_API_KEY 미설정으로 폴백 사용"
        return result

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_PRO_MODEL)
        prompt = f"""
너는 리스크 매니저야.
아래 4명 의견과 시장 데이터를 검토하고 한국어 JSON만 반환해.

[4명 의견]
{json.dumps(all_opinions, ensure_ascii=False)[:3500]}

[시장 데이터]
{json.dumps(market_data, ensure_ascii=False)[:2000]}

스키마:
{{
  "overbought_warnings":[{{"name":"종목명","position_52w":"91%","warning":"주의"}}],
  "hidden_risks":["리스크1","리스크2"],
  "stop_loss":{{"종목명":"-8% 이탈 시 재검토"}},
  "portfolio_risk":"낮음/보통/높음",
  "do_not":"지금 절대 하면 안 되는 것",
  "verdicts":{{"종목명":{{"vote":"홀드","reason":["이유1","이유2"]}}}},
  "summary":"한 줄 요약"
}}
"""
        response = model.generate_content(prompt)
        if logger and hasattr(response, "usage_metadata") and response.usage_metadata:
            logger.log(
                model=config.GEMINI_PRO_MODEL,
                agent="risk",
                input_tokens=int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0),
            )
        text = getattr(response, "text", "") or ""
        parsed = safe_json_parse(text)
        if parsed:
            parsed.setdefault("meta", {"mode": "gemini"})
            return parsed
        print("[WARN] risk: Gemini responded but JSON parse failed")
        print(f"[WARN] risk raw head: {text[:500]!r}")
    except Exception:
        print("[ERROR] risk Gemini call failed:")
        print(traceback.format_exc())

    if logger:
        logger.log(config.GEMINI_PRO_MODEL, "risk", input_tokens=0, output_tokens=0)
    result = _fallback(market_data)
    result["meta"] = {"mode": "fallback-on-error"}
    return result
