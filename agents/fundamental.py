"""Stage 3b: Fundamental analyst (이준혁)."""

from __future__ import annotations

import json
from typing import Any

import config

from .common import ANALYST_VOICE_RULES, format_analyst_comment, safe_float


def _us_dart_summary(stock: dict[str, Any]) -> str | None:
    rev = stock.get("revenue_eok")
    ni = stock.get("net_income_eok")
    parts: list[str] = []
    if rev is not None:
        parts.append(f"매출 약 {safe_float(rev):,.0f}억원")
    if ni is not None:
        parts.append(f"순이익 약 {safe_float(ni):,.0f}억원")
    return ", ".join(parts) if parts else None


def analyze_fundamental(
    supply_result: dict[str, Any], watchlist_data: dict[str, Any], logger: Any = None
) -> dict[str, Any]:
    """Score fundamentals from PER/PBR and available financials (KR DART / US yfinance)."""
    del watchlist_data
    scores: dict[str, dict[str, Any]] = {}

    for stock in supply_result.get("filtered_stocks", []):
        ticker = str(stock.get("ticker", ""))
        market = str(stock.get("market", "KR"))
        per = stock.get("per")
        pbr = stock.get("pbr")
        dart = stock.get("dart_summary") or (_us_dart_summary(stock) if market == "US" else None)

        if market == "KR" and (per is None or pbr is None):
            try:
                from data.kr_market import get_kr_fundamentals

                fin = get_kr_fundamentals(ticker) or {}
                per = per if per is not None else fin.get("per")
                pbr = pbr if pbr is not None else fin.get("pbr")
            except Exception:
                pass

        if market == "US" and per is None and pbr is None:
            try:
                from data.us_market import get_us_financials

                fin = get_us_financials(ticker) or {}
                per = fin.get("per")
                pbr = fin.get("pbr")
                if not dart:
                    dart = _us_dart_summary({**stock, **fin})
            except Exception:
                pass

        score = 50
        valuation = "N/A"
        comment_parts: list[str] = []

        if per is not None:
            per_v = safe_float(per, 0.0)
            if per_v > 0:
                comment_parts.append(f"PER {per_v:.1f}배")
                if per_v < 12:
                    score += 10
        if pbr is not None:
            pbr_v = safe_float(pbr, 0.0)
            if pbr_v > 0:
                comment_parts.append(f"PBR {pbr_v:.1f}배")
                if pbr_v < 1:
                    score += 15
                    valuation = "저평가"
                elif pbr_v < 2:
                    valuation = "적정"
                else:
                    valuation = "고평가"

        if dart:
            comment_parts.append(str(dart))
            score += 10
        elif per is None and pbr is None:
            valuation = "N/A"
            comment_parts.append("N/A")

        score = max(0, min(100, score))
        scores[ticker] = {
            "per": f"{safe_float(per):.1f}" if per is not None else "N/A",
            "pbr": f"{safe_float(pbr):.1f}" if pbr is not None else "N/A",
            "valuation": valuation,
            "dart_summary": str(dart) if dart else "N/A",
            "fundamental_score": score,
            "comment": ", ".join(comment_parts) if comment_parts else "N/A",
        }

    result: dict[str, Any] = {"fundamental_scores": scores, "meta": {"mode": "rules"}}

    if config.GEMINI_API_KEY and scores:
        from .gemini_client import generate_gemini_json

        prompt = f"""
당신은 PER·PBR로 밸류에이션을 설명하는 애널리스트 이준혁입니다.
주가 모멘텀·수급은 다루지 말고, 장부가치 대비 비싼지·싼지만 쉽게 설명하세요.
{ANALYST_VOICE_RULES}

예시 (이준혁 톤):
"PBR이 3.3으로 자산 대비 꽤 비싼 편이에요. 업종 평균보다 높아서 밸류 부담이 있어요. 실적이 뒷받침돼야 정당화되는 수준이에요."

아래 PER/PBR·실적 데이터만 사용. 추측 금지.
[종목]{json.dumps(list(scores.items()), ensure_ascii=False)[:3000]}

인사말·서론 없이 JSON만.
스키마: {{"fundamental_scores": {{"티커": {{"comment":"3문장","valuation":"저평가/적정/고평가","fundamental_score":0-100}}}}}}
"""
        parsed = generate_gemini_json(prompt, agent="fundamental", logger=logger)
        if parsed and isinstance(parsed.get("fundamental_scores"), dict):
            for ticker, row in parsed["fundamental_scores"].items():
                if ticker not in scores or not isinstance(row, dict):
                    continue
                if row.get("comment"):
                    scores[ticker]["comment"] = format_analyst_comment(str(row["comment"]))
                if row.get("valuation"):
                    scores[ticker]["valuation"] = str(row["valuation"])
                if row.get("fundamental_score") is not None:
                    scores[ticker]["fundamental_score"] = max(
                        0,
                        min(
                            100,
                            int(
                                safe_float(
                                    row["fundamental_score"],
                                    scores[ticker]["fundamental_score"],
                                )
                            ),
                        ),
                    )
            result["meta"]["mode"] = "rules+gemini"

    return result
