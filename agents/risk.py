"""Stage 4: Risk manager (강민서)."""

from __future__ import annotations

import json
from typing import Any

import config

from .common import ANALYST_VOICE_RULES, compute_stop_loss, distance_from_high_pct, format_analyst_comment, normalize_phase, safe_float


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
        stop_loss = compute_stop_loss(price, 0.94)

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
        if ticker.isdigit():
            assessments_map[ticker.zfill(6)] = entry

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

        stocks_for_prompt = [
            {
                "ticker": s.get("ticker"),
                "name": s.get("name"),
                "price": s.get("price"),
                "stop_loss": assessments_map.get(str(s.get("ticker")), {}).get("stop_loss"),
                "final_verdict": assessments_map.get(str(s.get("ticker")), {}).get("final_verdict"),
            }
            for s in supply_result.get("filtered_stocks", [])
        ]
        prompt = f"""
당신은 최종 리스크를 정리하는 리스크 매니저 강민서입니다.
4명 애널리스트 의견을 종합해, 초보자에게 옆에서 조언하듯 말해 주세요.
{ANALYST_VOICE_RULES}

예시 (강민서 톤):
"PBR 고평가에 시장도 불안한 상황이에요. 지금은 관망하는 게 나을 것 같아요. 혹시 보유 중이라면 1,503원 밑에서 손절하세요."

손절가(stop_loss)는 현재가×0.94 근처 원화 가격(예: 98,700원). comment에 손절 가격을 자연스럽게 넣으세요.
시장 국면이 위험회피면 분할·관망을 권하세요.
인사말·서론 없이 JSON만.

[매크로]{json.dumps({"phase": phase, "warning": risk_warning}, ensure_ascii=False)}
[종목]{json.dumps(stocks_for_prompt, ensure_ascii=False)[:3000]}

스키마: {{"risk_assessments": {{"티커": {{"comment":"리스크·관망·손절 3문장","final_verdict":"매수/홀드/매도","stop_loss":"98,700원"}}}}, "one_line_summary":"한줄"}}
"""
        parsed = generate_gemini_json(prompt, agent="risk", logger=logger)
        if parsed:
            if isinstance(parsed.get("risk_assessments"), dict):
                for ticker, row in parsed["risk_assessments"].items():
                    if ticker not in assessments_map or not isinstance(row, dict):
                        continue
                    if row.get("comment"):
                        assessments_map[ticker]["comment"] = format_analyst_comment(str(row["comment"]))
                    elif row.get("risk_comment"):
                        assessments_map[ticker]["comment"] = format_analyst_comment(
                            " ".join(
                                str(x)
                                for x in (row.get("risk_comment"), row.get("verdict_comment"))
                                if x
                            )
                        )
                    if row.get("final_verdict"):
                        assessments_map[ticker]["final_verdict"] = str(row["final_verdict"])
                    if row.get("stop_loss"):
                        sl = str(row["stop_loss"])
                        if "원" in sl and sl not in ("N/A", "n/a"):
                            assessments_map[ticker]["stop_loss"] = sl
            if parsed.get("one_line_summary"):
                result["one_line_summary"] = str(parsed["one_line_summary"])
            result["meta"]["mode"] = "rules+gemini"

    for stock in supply_result.get("filtered_stocks", []):
        ticker = str(stock.get("ticker", ""))
        keys = {ticker, ticker.zfill(6) if ticker.isdigit() else ticker}
        entry = None
        for k in keys:
            if k in assessments_map:
                entry = assessments_map[k]
                break
        if not entry:
            continue
        computed = compute_stop_loss(stock.get("price"), 0.94)
        sl = str(entry.get("stop_loss") or "")
        if computed != "N/A" and (not sl or sl in ("N/A", "n/a") or "원" not in sl):
            entry["stop_loss"] = computed

    return result
