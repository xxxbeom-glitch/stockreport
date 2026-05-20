"""Per-stock agent vote and comment resolution for HTML report."""

from __future__ import annotations

from typing import Any

from data.kr_market import get_kr_fundamentals

from .common import (
    ANALYST_VOICE_RULES,
    compute_stop_loss,
    distance_from_high_pct,
    fmt_foreign_net_eok,
    format_analyst_comment,
    safe_float,
    volume_flow_label,
)
from .supply_demand import KR_THEME_SECTORS, US_THEME_KEYWORDS, _theme_matches_favorable


def normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    if t.isdigit():
        return t.zfill(6)
    return t.upper()


def _dedupe_lines(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        text = str(p).strip()
        if not text or text in {"N/A", "None"} or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _analyst_reason(text_or_parts: Any, fallback: str) -> list[str]:
    if isinstance(text_or_parts, list):
        text = " ".join(_dedupe_lines([str(p) for p in text_or_parts]))
    else:
        text = str(text_or_parts or "")
    formatted = format_analyst_comment(text)
    return [formatted or fallback]


def score_to_vote(score: float) -> str:
    if score >= 65:
        return "매수"
    if score <= 42:
        return "매도"
    return "홀드"


def _enrich_stock_metrics(stock: dict[str, Any], ticker: str) -> dict[str, Any]:
    row = dict(stock)
    market = str(row.get("market", "KR")).upper()
    if market in {"KR", "KOSPI", "KOSDAQ"} and (row.get("per") is None or row.get("pbr") is None):
        fin = get_kr_fundamentals(ticker)
        if row.get("per") is None:
            row["per"] = fin.get("per")
        if row.get("pbr") is None:
            row["pbr"] = fin.get("pbr")
        if row.get("foreign_ownership") is None:
            row["foreign_ownership"] = fin.get("foreign_ownership")
    return row


def _find_supply_stock(pipeline: dict[str, Any], ticker: str) -> dict[str, Any]:
    key = normalize_ticker(ticker)
    for stock in (pipeline.get("supply") or {}).get("filtered_stocks", []):
        if normalize_ticker(str(stock.get("ticker", ""))) == key:
            return stock
    return {}


def _find_watchlist_stock(pipeline: dict[str, Any], ticker: str) -> dict[str, Any]:
    key = normalize_ticker(ticker)
    for stock in ((pipeline.get("watchlist_data") or {}).get("stocks", [])):
        if normalize_ticker(str(stock.get("ticker", ""))) == key:
            return stock
    return {}


def _grok_supply(ticker: str, supply: dict[str, Any]) -> dict[str, Any]:
    key = normalize_ticker(ticker)
    return (supply.get("grok_verdicts") or {}).get(key) or (supply.get("grok_verdicts") or {}).get(
        ticker
    ) or {}


def _grok_momentum(ticker: str, momentum: dict[str, Any]) -> dict[str, Any]:
    key = normalize_ticker(ticker)
    return (momentum.get("grok_verdicts") or {}).get(key) or (momentum.get("grok_verdicts") or {}).get(
        ticker
    ) or {}


def _index_moves_summary(pipeline: dict[str, Any] | None) -> str:
    indices = ((pipeline or {}).get("watchlist_data") or {}).get("indices") or {}
    bits: list[str] = []
    for name in ("KOSPI", "KOSDAQ", "S&P500", "NASDAQ"):
        row = indices.get(name) or {}
        chg = row.get("change")
        if chg and chg != "N/A":
            bits.append(f"{name} {chg}")
    if bits:
        return f"주요 지수는 {', '.join(bits[:3])} 등으로 움직이고 있어요."
    return ""


def _macro_narrative(
    stock: dict[str, Any], macro: dict[str, Any], pipeline: dict[str, Any] | None
) -> str:
    if macro.get("stock_comments"):
        key = normalize_ticker(str(stock.get("ticker", "")))
        sc = macro["stock_comments"].get(key) or macro["stock_comments"].get(stock.get("ticker"))
        if sc:
            return format_analyst_comment(sc)

    phase = str(macro.get("market_phase", "중립"))
    theme = str(stock.get("theme", "관심 종목"))
    market = str(stock.get("market", "KR"))
    wv = (macro.get("watchlist_verdict") or {}).get("KR" if market == "KR" else "US", "")

    parts = [f"지금 시장 전체가 {phase} 분위기예요."]
    idx_line = _index_moves_summary(pipeline)
    if idx_line:
        parts.append(idx_line)
    elif macro.get("market_phase_reason"):
        parts.append(str(macro["market_phase_reason"]))

    if wv and wv != "N/A":
        parts.append(str(wv))
    elif phase == "위험회피":
        parts.append(f"이런 환경에서는 {theme} 쪽이 변동성에 더 취약할 수 있어요.")
    else:
        parts.append(f"{theme} 테마는 지금 국면에서 선별적으로 보는 편이 낫겠어요.")

    return format_analyst_comment(" ".join(parts[:3]))


def _supply_narrative(stock: dict[str, Any], grok: dict[str, Any]) -> str:
    if stock.get("supply_comment"):
        return format_analyst_comment(stock["supply_comment"])
    if grok.get("comment"):
        return format_analyst_comment(grok["comment"])

    parts: list[str] = []
    foreign = stock.get("foreign_net")
    if foreign is not None:
        fn = safe_float(foreign, 0.0)
        eok = fmt_foreign_net_eok(foreign).replace("+", "")
        if fn > 0:
            parts.append(f"외국인이 오늘 {eok}원어치 사들였어요.")
        elif fn < 0:
            parts.append(f"외국인이 오늘 {eok}원어치 팔아낸 흐름이에요.")
        else:
            parts.append("외국인 수급은 뚜렷한 방향이 없어요.")

    vol = safe_float(stock.get("volume_ratio"), 0.0)
    if vol >= 2:
        parts.append(f"거래량도 평균의 {vol:.0f}배나 터졌고요.")
        if safe_float(stock.get("change_rate"), 0.0) > 0:
            parts.append("큰손들이 조용히 담는 신호로 볼 수 있어요.")
        else:
            parts.append("매도 압력이 섞인 거래량이라 주의가 필요해요.")
    elif stock.get("conclusion_strength") is not None:
        parts.append(
            f"체결강도는 {safe_float(stock.get('conclusion_strength')):.0f}%라 "
            f"{'매수세가 우위예요.' if safe_float(stock.get('conclusion_strength')) >= 100 else '수급이 약한 편이에요.'}"
        )

    if grok.get("supply_direction"):
        parts.append(str(grok["supply_direction"]))
    elif grok.get("x_sentiment"):
        parts.append(str(grok["x_sentiment"]))

    return format_analyst_comment(" ".join(parts)) or "수급 데이터가 부족해 판단을 보류할게요."


def _momentum_narrative(
    stock: dict[str, Any], momentum_row: dict[str, Any], grok: dict[str, Any]
) -> str:
    if momentum_row.get("momentum_comment"):
        return format_analyst_comment(momentum_row["momentum_comment"])
    if grok.get("comment"):
        return format_analyst_comment(grok["comment"])

    vol = safe_float(stock.get("volume_ratio"), 0.0)
    chg = safe_float(stock.get("change_rate"), 0.0)
    parts: list[str] = []

    if vol >= 3 and chg > 0:
        parts.append("거래량이 폭발하면서 주가가 오르고 있어요.")
        parts.append("파는 사람보다 사는 사람이 훨씬 많은 상황이에요.")
        parts.append("단기 상승 모멘텀이 살아있어요.")
    elif vol >= 3 and chg < 0:
        parts.append("거래량은 크지만 가격은 밀리고 있어요.")
        parts.append("차익실현 매물이 나오는 구간으로 보여요.")
        parts.append("단기 반등 전까지는 관망이 나을 수 있어요.")
    else:
        pos = momentum_row.get("position_52w")
        if pos and pos != "N/A":
            parts.append(f"52주 밴드 기준으로는 {pos} 구간에 있어요.")
        parts.append(volume_flow_label(vol, chg) + " 흐름이에요.")
        trend = momentum_row.get("trend")
        if trend:
            parts.append(f"단기 추세는 {trend} 쪽으로 읽혀요.")

    if grok.get("position_52w_analysis"):
        parts.append(str(grok["position_52w_analysis"]))

    return format_analyst_comment(" ".join(parts)) or "모멘텀 신호가 뚜렷하지 않아요."


def _fundamental_narrative(stock: dict[str, Any], f: dict[str, Any]) -> str:
    if f.get("comment") and f.get("comment") != "N/A":
        return format_analyst_comment(f["comment"])

    pbr_v = safe_float(stock.get("pbr") or f.get("pbr"), 0.0)
    per_v = safe_float(stock.get("per") or f.get("per"), 0.0)
    valuation = str(f.get("valuation", "N/A"))

    parts: list[str] = []
    if pbr_v > 0:
        parts.append(f"PBR이 {pbr_v:.1f}로 자산 대비 {'꽤 비싼' if pbr_v >= 2 else '적당한' if pbr_v >= 1 else '싼'} 편이에요.")
    if per_v > 0:
        parts.append(f"PER은 {per_v:.1f}배라 이익 대비 주가 수준을 함께 봐야 해요.")
    if valuation == "고평가":
        parts.append("업종 평균보다 부담이 있어 실적 뒷받침이 필요한 구간이에요.")
    elif valuation == "저평가":
        parts.append("장부가치 대비 매력이 있어 중장기 관점에서는 긍정적으로 볼 수 있어요.")
    elif valuation == "적정":
        parts.append("밸류에이션은 크게 부담되지 않는 수준이에요.")

    return format_analyst_comment(" ".join(parts)) or "PER·PBR 데이터가 없어 밸류 판단이 어려워요."


def _risk_narrative(stock: dict[str, Any], r: dict[str, Any], pipeline: dict[str, Any] | None) -> str:
    if r.get("comment"):
        return format_analyst_comment(r["comment"])

    price = stock.get("price")
    stop = compute_stop_loss(price, 0.94)
    sl_display = stop.replace(",", "") if stop != "N/A" else ""

    fundamental = ((pipeline or {}).get("fundamental") or {}).get("fundamental_scores") or {}
    f_row = fundamental.get(normalize_ticker(str(stock.get("ticker", "")))) or {}
    valuation = str(f_row.get("valuation", ""))
    phase = str(((pipeline or {}).get("macro") or {}).get("market_phase", "중립"))

    parts: list[str] = []
    if valuation == "고평가":
        parts.append("PBR·밸류 부담이 있는 종목이에요.")
    if phase == "위험회피":
        parts.append("시장 전체도 불안한 분위기라 보수적으로 가는 게 좋아요.")

    verdict = str(r.get("final_verdict", "홀드"))
    if r.get("risk_comment") and r.get("risk_comment") != "N/A":
        parts.append(str(r["risk_comment"]))
    elif verdict == "매도":
        parts.append("지금은 관망하거나 비중을 줄이는 편이 낫겠어요.")
    elif verdict == "매수":
        parts.append("진입은 가능하지만 분할 매수를 권해요.")
    else:
        parts.append("급하게 추격하기보다 지켜보는 게 나을 것 같아요.")

    if sl_display != "N/A":
        parts.append(f"혹시 보유 중이라면 {sl_display} 밑에서 손절하세요.")

    return format_analyst_comment(" ".join(parts))


def _macro_vote(
    stock: dict[str, Any], macro: dict[str, Any], pipeline: dict[str, Any] | None
) -> tuple[str, list[str]]:
    market = str(stock.get("market", "KR"))
    theme = str(stock.get("theme", ""))
    phase = str(macro.get("market_phase", "중립"))
    favorable = [str(s) for s in macro.get("favorable_sectors", [])]
    unfavorable = [str(s) for s in macro.get("unfavorable_sectors", [])]
    in_fav = _theme_matches_favorable(theme, market, favorable) if favorable else True
    in_unfav = any(
        s in unfavorable
        for s in (KR_THEME_SECTORS.get(theme, []) if market == "KR" else US_THEME_KEYWORDS.get(theme, [theme]))
    )

    if phase == "강세" and in_fav and not in_unfav:
        vote = "매수"
    elif phase == "위험회피" and (in_unfav or not in_fav):
        vote = "매도"
    elif phase == "위험회피":
        vote = "홀드"
    elif phase == "강세":
        vote = "매수"
    else:
        vote = "홀드"

    return vote, _analyst_reason(_macro_narrative(stock, macro, pipeline), "매크로 관점에서 뚜렷한 신호는 없어요.")


def _supply_vote(ticker: str, stock: dict[str, Any], supply: dict[str, Any]) -> tuple[str, list[str]]:
    grok = _grok_supply(ticker, supply)
    score = safe_float(stock.get("score"), 0.0)
    vote = str(grok.get("vote") or stock.get("grok_vote") or (score_to_vote(score) if score else "홀드"))
    return vote, _analyst_reason(_supply_narrative(stock, grok), "수급 데이터가 부족해요.")


def _momentum_vote(ticker: str, stock: dict[str, Any], momentum: dict[str, Any]) -> tuple[str, list[str]]:
    key = normalize_ticker(ticker)
    m = (momentum.get("momentum_scores") or {}).get(key) or {}
    grok = _grok_momentum(ticker, momentum)
    mom_score = safe_float(m.get("momentum_score"), 50.0)
    vote = str(grok.get("vote") or m.get("grok_vote") or score_to_vote(mom_score))
    return vote, _analyst_reason(_momentum_narrative(stock, m, grok), "모멘텀 신호가 약해요.")


def _fundamental_vote(ticker: str, stock: dict[str, Any], fundamental: dict[str, Any]) -> tuple[str, list[str]]:
    key = normalize_ticker(ticker)
    f = (fundamental.get("fundamental_scores") or {}).get(key) or {}
    stock = _enrich_stock_metrics(stock, ticker)

    per_v = stock.get("per")
    pbr_v = stock.get("pbr")
    if not f and (per_v is not None or pbr_v is not None):
        per_f = safe_float(per_v, 0.0)
        pbr_f = safe_float(pbr_v, 0.0)
        valuation = "적정"
        if pbr_f > 0 and pbr_f < 1:
            valuation = "저평가"
        elif pbr_f >= 2:
            valuation = "고평가"
        f = {
            "per": f"{per_f:.1f}" if per_f else "N/A",
            "pbr": f"{pbr_f:.1f}" if pbr_f else "N/A",
            "valuation": valuation,
            "comment": "",
            "fundamental_score": 55 if valuation == "적정" else (70 if valuation == "저평가" else 40),
        }

    fs = safe_float(f.get("fundamental_score"), 50.0)
    valuation = str(f.get("valuation", "N/A"))
    if valuation == "저평가":
        vote = "매수"
    elif valuation == "고평가":
        vote = "매도"
    else:
        vote = score_to_vote(fs)

    return vote, _analyst_reason(_fundamental_narrative(stock, f), "펀더멘털 데이터가 부족해요.")


def _risk_vote(
    ticker: str, risk: dict[str, Any], stock: dict[str, Any], pipeline: dict[str, Any] | None
) -> tuple[str, list[str]]:
    key = normalize_ticker(ticker)
    r = (risk.get("risk_assessments") or {}).get(key) or (risk.get("risk_assessments") or {}).get(
        ticker
    ) or {}

    price = stock.get("price")
    stop = compute_stop_loss(price, 0.94)

    if not r:
        high = stock.get("high_52")
        dist = distance_from_high_pct(price, high)
        if dist is not None and dist > -5:
            return "매도", _analyst_reason(
                f"52주 고점 근처라 변동성이 커요. 지금은 들어가기보다 기다리는 편이 낫겠어요. "
                f"보유 중이라면 {stop.replace(',', '')} 밑에서 손절하세요.",
                "추격 매수는 피하는 게 좋아요.",
            )
        return "홀드", _analyst_reason(
            f"리스크는 크지 않지만 방향 확인이 필요해요. 분할 접근을 권해요. "
            f"손절 참고가는 {stop.replace(',', '')} 근처예요.",
            "리스크 데이터가 제한적이에요.",
        )

    vote = str(r.get("final_verdict", "홀드"))
    sl = str(r.get("stop_loss") or "")
    if sl in ("", "N/A", "n/a") or "원" not in sl:
        r = {**r, "stop_loss": stop}

    return vote, _analyst_reason(_risk_narrative(stock, r, pipeline), f"손절 참고 {stop}이에요.")


def resolve_stock_agent_vote(
    agent_key: str,
    ticker: str,
    name: str,
    stock_hint: dict[str, Any],
    pipeline: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Return vote + comment lines for one agent and one stock."""
    if not pipeline:
        summary = str((stock_hint or {}).get("summary", "")).strip()
        return "홀드", _analyst_reason(summary, "의견 없음")

    pipe_stock = _find_supply_stock(pipeline, ticker) or _find_watchlist_stock(pipeline, ticker) or stock_hint
    pipe_stock = _enrich_stock_metrics(pipe_stock, ticker)

    if agent_key == "macro":
        return _macro_vote(pipe_stock, pipeline.get("macro") or {}, pipeline)
    if agent_key == "supply":
        return _supply_vote(ticker, pipe_stock, pipeline.get("supply") or {})
    if agent_key == "momentum":
        return _momentum_vote(ticker, pipe_stock, pipeline.get("momentum") or {})
    if agent_key == "fundamental":
        return _fundamental_vote(ticker, pipe_stock, pipeline.get("fundamental") or {})
    if agent_key == "risk":
        return _risk_vote(ticker, pipeline.get("risk") or {}, pipe_stock, pipeline)

    return "홀드", ["알 수 없는 에이전트"]
