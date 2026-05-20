"""Stage 3a: Momentum quant analyst (Chris Yoon) — Grok + X real-time search."""

from __future__ import annotations

import json
from typing import Any

import config
from config import VOLUME_FIRE

from .common import position_52w_label, position_52w_pct, safe_float


def _grok_momentum_analysis(
    stocks: list[dict[str, Any]],
    supply_result: dict[str, Any],
    logger: Any = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Grok + x_search: 단기 모멘텀, X 핫 여부, 52주 추세, 매수/홀드/매도."""
    if not config.GROK_API_KEY or not stocks:
        return None, {"mode": "disabled", "x_search_enabled": False}

    from .grok_client import grok_x_search_json

    stock_lines = [
        f"- {s.get('name')}({s.get('ticker')}): 등락={s.get('change_rate')}%, "
        f"거래량배수={s.get('volume_ratio')}, 52주저={s.get('low_52')}, 52주고={s.get('high_52')}, 가격={s.get('price')}"
        for s in stocks[:8]
    ]

    prompt = f"""
당신은 철저하게 숫자와 모멘텀에 기반하는 퀀트 애널리스트 Chris Yoon입니다.
외국인·기관 수급·체결강도는 언급하지 말 것. 오직 52주 위치, 등락률, 거래량배수, 추세만.
거래량 급등이 매집인지 차익실현(설거지)인지 반드시 판단.
position_52w_analysis, x_buzz, momentum_direction 각 40자 이내 1문장(한국어).
X 검색은 보조만 사용. 반드시 x_search 결과 기반. 추측 금지.

[시장 국면] {supply_result.get("market_phase", "중립")}
[분석 종목]
{chr(10).join(stock_lines)}

각 종목마다 다음을 분석:
1. 단기 모멘텀 방향 (상승/하락/보합)과 강도
2. X에서 지금 핫하게 언급되는 종목인지 (is_x_hot: true/false, 근거)
3. 52주 고저 대비 현재 위치 기반 추세 판단
4. 모멘텀 관점 매수/홀드/매도 의견 (vote는 "매수", "홀드", "매도" 중 하나)

JSON만 반환:
{{
  "top_theme": "지금 X에서 가장 강한 테마 한줄",
  "summary": "모멘텀 전체 한줄",
  "verdicts": {{
    "티커": {{
      "name": "종목명",
      "vote": "매수",
      "momentum_direction": "상승",
      "is_x_hot": true,
      "position_52w_analysis": "52주 위치·매집/차익 40자 이내",
      "x_buzz": "X 모멘텀 40자 이내",
      "reasons": ["이유1", "이유2"]
    }}
  }}
}}
"""
    return grok_x_search_json(prompt, agent="momentum", logger=logger, model="grok-3")


def _merge_grok_momentum(result: dict[str, Any], grok: dict[str, Any] | None) -> None:
    if not grok:
        return

    if grok.get("summary"):
        result["summary"] = str(grok["summary"])
    if grok.get("top_theme"):
        result["top_theme_x"] = str(grok["top_theme"])
        result["x_momentum_buzz"] = str(grok["top_theme"])

    verdicts = grok.get("verdicts") or {}
    result["grok_verdicts"] = verdicts
    scores = result.get("momentum_scores") or {}

    for key, v in verdicts.items():
        if not isinstance(v, dict):
            continue
        ticker = str(key)
        row = scores.get(ticker) or scores.get(ticker.zfill(6))
        if not row:
            continue
        from .common import truncate_comment

        row["grok_vote"] = v.get("vote")
        row["momentum_direction"] = truncate_comment(v.get("momentum_direction"))
        row["is_x_hot"] = v.get("is_x_hot")
        row["x_momentum_comment"] = truncate_comment(v.get("x_buzz") or v.get("x_momentum_comment"))
        row["position_52w_analysis"] = truncate_comment(v.get("position_52w_analysis"))


def analyze_momentum(
    supply_result: dict[str, Any], watchlist_data: dict[str, Any], logger: Any = None
) -> dict[str, Any]:
    """Score momentum for supply-filtered stocks; enrich with Grok X search."""
    del watchlist_data
    stocks_by_ticker = {str(s.get("ticker")): s for s in supply_result.get("filtered_stocks", [])}
    scores: dict[str, dict[str, Any]] = {}

    for ticker, stock in stocks_by_ticker.items():
        price = stock.get("price")
        low = stock.get("low_52")
        high = stock.get("high_52")
        pos_pct = position_52w_pct(price, low, high)
        pos_label = position_52w_label(price, low, high)
        vol = safe_float(stock.get("volume_ratio"), 0.0)
        change = safe_float(stock.get("change_rate"), 0.0)

        score = 50
        comment_parts: list[str] = []
        volume_surge = vol >= VOLUME_FIRE

        if pos_pct is not None:
            if pos_pct >= 90:
                score -= 15
                comment_parts.append("52주 고점 근접, 과열 주의")
            elif pos_pct <= 30:
                score += 20
                comment_parts.append("52주 저점 부근, 반등 여지")
            else:
                comment_parts.append(f"52주 {pos_label} 위치")

        if change > 1:
            score += 15
            trend = "상승"
        elif change < -1:
            score -= 10
            trend = "하락"
        else:
            trend = "보합"

        from .common import volume_flow_label

        flow = volume_flow_label(vol, change)
        comment_parts.append(flow)

        if vol >= VOLUME_FIRE:
            score += 20
        elif vol >= 2:
            score += 10

        score = max(0, min(100, score))
        scores[ticker] = {
            "position_52w": pos_label,
            "trend": trend,
            "volume_surge": volume_surge,
            "momentum_score": score,
            "comment": ", ".join(comment_parts) if comment_parts else "N/A",
        }

    stocks_list = list(stocks_by_ticker.values())
    result: dict[str, Any] = {
        "momentum_scores": scores,
        "x_momentum_buzz": "N/A",
        "grok_verdicts": {},
        "meta": {"mode": "rules", "x_search_enabled": False},
    }

    grok_targets = stocks_list if stocks_list else []
    grok_parsed, grok_meta = _grok_momentum_analysis(grok_targets, supply_result, logger=logger)
    result["meta"] = {**result["meta"], **grok_meta}
    if grok_meta.get("x_search_enabled"):
        result["meta"]["mode"] = "rules+grok+x_search"
    _merge_grok_momentum(result, grok_parsed)

    return result
