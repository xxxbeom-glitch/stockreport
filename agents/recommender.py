"""Stage 5: Final buy recommendations."""

from __future__ import annotations

import json
from typing import Any

import ai_models
import config

from .common import (
    compute_stop_loss,
    fmt_foreign_net_eok,
    fmt_krw,
    fmt_pct,
    safe_float,
    volume_emoji,
)


def _resolve_stop_loss(risk: dict[str, Any], stock: dict[str, Any]) -> str:
    sl = str(risk.get("stop_loss") or "")
    if sl and sl not in ("N/A", "n/a") and "원" in sl:
        return sl
    computed = compute_stop_loss(stock.get("price"), 0.94)
    return computed if computed != "N/A" else "N/A"


def get_recommendations(
    macro_result: dict[str, Any],
    supply_result: dict[str, Any],
    momentum_result: dict[str, Any],
    fundamental_result: dict[str, Any],
    risk_result: dict[str, Any],
    watchlist_data: dict[str, Any],
    logger: Any = None,
) -> dict[str, Any]:
    """Aggregate scores and emit top buy recommendations."""
    del macro_result, logger
    momentum_scores = momentum_result.get("momentum_scores") or {}
    fundamental_scores = fundamental_result.get("fundamental_scores") or {}
    risk_map = risk_result.get("risk_assessments") or {}

    candidates: list[dict[str, Any]] = []
    for stock in supply_result.get("filtered_stocks", []):
        ticker = str(stock.get("ticker", ""))
        risk = risk_map.get(ticker) or risk_map.get(ticker.zfill(6) if ticker.isdigit() else ticker) or {}
        if risk.get("final_verdict") != "매수":
            continue

        supply_s = safe_float(stock.get("score"), 0.0)
        mom_s = safe_float((momentum_scores.get(ticker) or {}).get("momentum_score"), 0.0)
        fund_s = safe_float((fundamental_scores.get(ticker) or {}).get("fundamental_score"), 0.0)
        total = round(supply_s * 0.4 + mom_s * 0.3 + fund_s * 0.3, 1)

        if total < 70:
            continue

        market = str(stock.get("market", "KR"))
        vol = safe_float(stock.get("volume_ratio"), 0.0)
        price = stock.get("price")
        if market == "US":
            price_display = fmt_krw(stock.get("price_krw")) if stock.get("price_krw") else "N/A"
        else:
            price_display = fmt_krw(price)

        m_row = momentum_scores.get(ticker, {})
        f_row = fundamental_scores.get(ticker, {})
        strength = stock.get("conclusion_strength")
        pos = m_row.get("position_52w", "N/A")

        candidates.append(
            {
                "ticker": ticker,
                "name": stock.get("name"),
                "market": market,
                "price": price_display,
                "change_rate": fmt_pct(stock.get("change_rate")),
                "volume_ratio": f"{vol:.0f}배" if vol else "N/A",
                "volume_emoji": volume_emoji(vol),
                "foreign_net": fmt_foreign_net_eok(stock.get("foreign_net")),
                "conclusion_strength": f"{safe_float(strength):.0f}%" if strength is not None else "N/A",
                "position_52w": pos,
                "per": f_row.get("per", "N/A"),
                "pbr": f_row.get("pbr", "N/A"),
                "foreign_ownership": (
                    f"{safe_float(stock.get('foreign_ownership')):.1f}%"
                    if stock.get("foreign_ownership") is not None
                    else "N/A"
                ),
                "total_score": total,
                "buy_reason": _buy_reason(stock, m_row, f_row, risk),
                "verdict_comment": risk.get("verdict_comment", "N/A"),
                "stop_loss": _resolve_stop_loss(risk, stock),
            }
        )

    candidates.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    top = candidates[:5]

    if not top:
        return {
            "buy_recommendations": [],
            "message": "오늘은 관망이 답입니다",
            "total_scanned": watchlist_data.get("total_scanned", 0),
            "total_passed": 0,
            "meta": {"mode": "rules"},
        }

    result: dict[str, Any] = {
        "buy_recommendations": top,
        "total_scanned": watchlist_data.get("total_scanned", 0),
        "total_passed": len(top),
        "meta": {"mode": "rules"},
    }

    if config.GEMINI_API_KEY or ai_models.DEEPSEEK_API_KEY:
        from .llm_router import generate_vote_json

        prompt = f"""
투자 추천 애널리스트로 아래 매수 후보의 buy_reason을 초보자용 3~4줄로 다듬어 JSON만 반환하세요.
[후보]{json.dumps(top, ensure_ascii=False)[:4000]}

스키마: {{"buy_recommendations": [{{"ticker":"","buy_reason":"3~4줄"}}]}}
"""
        parsed, llm_meta = generate_vote_json(prompt, agent="recommender", logger=logger)
        if parsed and isinstance(parsed.get("buy_recommendations"), list):
            result["meta"]["llm"] = llm_meta
            by_ticker = {str(r.get("ticker")): r for r in parsed["buy_recommendations"] if r.get("ticker")}
            for row in top:
                gem = by_ticker.get(str(row.get("ticker")))
                if gem and gem.get("buy_reason"):
                    row["buy_reason"] = str(gem["buy_reason"])[:500]
            result["meta"]["mode"] = f"rules+{llm_meta.get('engine', 'llm')}"

    return result


def _buy_reason(
    stock: dict[str, Any],
    momentum: dict[str, Any],
    fundamental: dict[str, Any],
    risk: dict[str, Any],
) -> str:
    theme = stock.get("theme", "관심")
    name = stock.get("name", stock.get("ticker", ""))
    lines = [
        f"{name}은(는) {theme} 테마에서 오늘 수급과 모멘텀이 함께 붙은 종목이에요.",
    ]
    mom = momentum.get("comment", "")
    if mom and mom != "N/A":
        lines.append(mom.rstrip(".") + "입니다.")
    fund = fundamental.get("comment", "")
    if fund and fund != "N/A":
        lines.append(f"밸류에이션은 {fund} 쪽으로 봅니다.")
    verdict = risk.get("verdict_comment", "")
    if verdict and verdict != "N/A":
        lines.append(verdict.rstrip(".") + ".")
    text = "\n".join(lines[:4])
    return text[:500] if text else "조건을 충족한 관심 종목입니다."
