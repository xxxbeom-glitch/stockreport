"""Stage 4: Risk manager (강민서)."""

from __future__ import annotations

import json
from typing import Any

import config

from .common import distance_from_high_pct, fmt_krw, normalize_phase, safe_float


def _risk_level(base: str, phase: str) -> str:
    order = ["낮음", "보통", "높음"]
    idx = order.index(base) if base in order else 1
    if phase == "위험회피":
        idx = min(2, idx + 1)
    return order[idx]


def analyze_risk(
    macro_result: dict[str, Any],
    supply_result: dict[str, Any],
    momentum_result: dict[str, Any],
    fundamental_result: dict[str, Any],
    watchlist_data: dict[str, Any],
    logger: Any = None,
) -> dict[str, Any]:
    """Assess risk and verdict per filtered stock."""
    del watchlist_data
    phase = normalize_phase(str(macro_result.get("market_phase", "중립")))
    momentum_scores = momentum_result.get("momentum_scores") or {}
    fundamental_scores = fundamental_result.get("fundamental_scores") or {}

    assessments_map: dict[str, dict[str, Any]] = {}

    for stock in supply_result.get("filtered_stocks", []):
        ticker = str(stock.get("ticker", ""))
        m = momentum_scores.get(ticker, {})
        f = fundamental_scores.get(ticker, {})
        price = stock.get("price")
        high = stock.get("high_52")
        dist_hi = distance_from_high_pct(price, high)

        base_risk = "보통"
        if dist_hi is not None and dist_hi > -5:
            base_risk = "높음"
        elif dist_hi is not None and dist_hi < -15:
            base_risk = "낮음"

        risk_level = _risk_level(base_risk, phase)
        stop_loss = "N/A"
        if stock.get("market") == "KR" and price:
            stop = safe_float(price, 0.0) * 0.92
            stop_loss = fmt_krw(stop)

        mom = safe_float(m.get("momentum_score"), 50.0)
        fund = safe_float(f.get("fundamental_score"), 50.0)
        supply_score = safe_float(stock.get("score"), 0.0)

        if risk_level == "높음" or mom < 45:
            verdict = "매도"
            verdict_comment = "조금 더 기다리세요"
        elif supply_score >= 70 and mom >= 55 and fund >= 50:
            verdict = "매수"
            verdict_comment = "지금 들어가기 좋은 구간"
        else:
            verdict = "홀드"
            verdict_comment = "지금 가진 거 들고 기다리세요"

        risk_comment = "N/A"
        if dist_hi is not None:
            risk_comment = f"고점 대비 {dist_hi:+.1f}%, 손절선 {stop_loss} 설정 권장"

        entry = {
            "risk_level": risk_level,
            "stop_loss": stop_loss,
            "risk_comment": risk_comment,
            "final_verdict": verdict,
            "verdict_comment": verdict_comment,
        }
        assessments_map[ticker] = entry

    risk_warning = str(macro_result.get("market_phase_reason", "N/A"))
    if phase == "위험회피":
        risk_warning = "변동성 확대 구간 — 신규 매수는 소량·분할만 권장"

    one_line = f"시장 국면 {phase}"
    fav = macro_result.get("favorable_sectors") or []
    if fav:
        one_line += f", 유입 섹터: {', '.join(fav[:3])}"

    result: dict[str, Any] = {
        "risk_assessments": assessments_map,
        "risk_warning": risk_warning,
        "one_line_summary": one_line,
        "meta": {"mode": "rules"},
    }

    if config.GEMINI_API_KEY and assessments_map:
        from .gemini_client import generate_gemini_json

        prompt = f"""
리스크 매니저로 아래 종목 리스크 평가를 검토해 JSON으로 보완하세요. 초보자도 이해하는 쉬운 말.
[매크로]{json.dumps({"phase": phase, "warning": risk_warning}, ensure_ascii=False)}
[평가]{json.dumps(assessments_map, ensure_ascii=False)[:3000]}

스키마: {{"risk_assessments": {{"티커": {{"risk_comment":"한줄","verdict_comment":"한줄","final_verdict":"매수/홀드/매도"}}}}, "one_line_summary":"한줄"}}
"""
        parsed = generate_gemini_json(prompt, agent="risk", logger=logger)
        if parsed:
            if isinstance(parsed.get("risk_assessments"), dict):
                for ticker, row in parsed["risk_assessments"].items():
                    if ticker not in assessments_map or not isinstance(row, dict):
                        continue
                    for key in ("risk_comment", "verdict_comment", "final_verdict"):
                        if row.get(key):
                            assessments_map[ticker][key] = str(row[key])
            if parsed.get("one_line_summary"):
                result["one_line_summary"] = str(parsed["one_line_summary"])
            result["meta"]["mode"] = "rules+gemini"

    return result
