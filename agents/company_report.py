"""Per-company draft report for hot volume names (draft-tier models)."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json
from typing import Any

import ai_models
import config
from utils.retry import retry

from .llm_router import generate_draft_json


def _fallback(ticker: str, name: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": name,
        "one_liner": f"{name}은(는) 거래량 급증으로 단기 관심이 집중된 종목입니다.",
        "why_hot": "거래량이 평소 대비 크게 늘며 시장 참여자들의 관심이 몰리고 있습니다.",
        "business": "핵심 사업 정보를 추가 수집 중입니다.",
        "strength": "유동성 확대로 가격 반응성이 높아진 구간입니다.",
        "risk": "급등 후 변동성 확대 및 되돌림 리스크에 유의해야 합니다.",
        "verdict": "홀드",
        "target_comment": "추가 데이터 확인 전 보수적 접근을 권장합니다.",
        "meta": {"mode": "fallback"},
    }


@retry(max_attempts=2, delay_sec=1.0)
def generate_company_report(
    ticker: str,
    name: str,
    market: str = "KOSPI",
    *,
    logger: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a short Korean company report via draft-tier LLM (DeepSeek flash → Gemini fallback)."""
    if not config.GEMINI_API_KEY and not ai_models.DEEPSEEK_API_KEY:
        result = _fallback(ticker, name)
        if logger:
            logger.log(ai_models.DEEPSEEK_DRAFT_MODEL, "company_report", input_tokens=0, output_tokens=0)
        return result

    context = extra or {}
    prompt = f"""
너는 주식 리서치 애널리스트야. 아래 종목에 대해 초보 투자자도 이해할 수 있게 한국어 JSON만 반환해.

종목: {name} ({ticker}) / 시장: {market}
참고 데이터: {json.dumps(context, ensure_ascii=False)[:2000]}

스키마:
{{
  "one_liner": "한줄요약",
  "why_hot": "오늘 거래량 급등 이유",
  "business": "핵심사업 2~3줄",
  "strength": "강점",
  "risk": "주요 리스크",
  "verdict": "매수/홀드/매도",
  "target_comment": "단기 관점 코멘트"
}}
"""
    parsed, llm_meta = generate_draft_json(prompt, agent="company_report", logger=logger)
    if parsed:
        parsed.setdefault("ticker", ticker)
        parsed.setdefault("name", name)
        parsed.setdefault("market", market)
        parsed.setdefault("meta", {"mode": f"draft+{llm_meta.get('engine', 'llm')}", "llm": llm_meta})
        return parsed

    result = _fallback(ticker, name)
    result["meta"] = {"mode": "fallback-on-error"}
    if logger:
        logger.log(ai_models.DEEPSEEK_DRAFT_MODEL, "company_report", input_tokens=0, output_tokens=0)
    return result
