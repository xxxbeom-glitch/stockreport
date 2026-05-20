"""Per-stock agent vote and comment resolution for HTML report."""

from __future__ import annotations

from typing import Any

from data.kr_market import get_kr_fundamentals

from .common import (
    compute_stop_loss,
    distance_from_high_pct,
    fmt_foreign_net_eok,
    fmt_krw,
    safe_float,
    truncate_comment,
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


def _one_comment(parts: list[str], fallback: str = "N/A") -> list[str]:
    merged = " · ".join(_dedupe_lines(parts))
    short = truncate_comment(merged)
    return [short or fallback]


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


def _macro_vote(stock: dict[str, Any], macro: dict[str, Any]) -> tuple[str, list[str]]:
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

    wv = (macro.get("watchlist_verdict") or {}).get("KR" if market == "KR" else "US", "")
    line = ""
    if wv and wv != "N/A":
        line = truncate_comment(str(wv))
    elif in_unfav and unfavorable:
        line = f"{theme} 유출 섹터 영향"
    elif in_fav and favorable:
        line = f"{phase}, {favorable[0]} 유입 우호"
    else:
        line = truncate_comment(macro.get("market_phase_reason", "")) or f"시장 {phase}"

    return vote, _one_comment([line], "매크로 관점 중립")


def _supply_vote(ticker: str, stock: dict[str, Any], supply: dict[str, Any]) -> tuple[str, list[str]]:
    grok = _grok_supply(ticker, supply)
    score = safe_float(stock.get("score"), 0.0)
    vote = str(grok.get("vote") or stock.get("grok_vote") or (score_to_vote(score) if score else "홀드"))

    parts: list[str] = []
    foreign = stock.get("foreign_net")
    if foreign is not None:
        fn = safe_float(foreign, 0.0)
        parts.append(
            f"외국인 {'순매수' if fn > 0 else '순매도'} {fmt_foreign_net_eok(foreign)}"
        )

    strength = stock.get("conclusion_strength")
    if strength is not None:
        parts.append(f"체결강도 {safe_float(strength):.0f}%")

    vol = stock.get("volume_ratio")
    if vol is not None:
        parts.append(f"거래량 {safe_float(vol):.1f}배")

    if grok.get("supply_direction"):
        parts.append(str(grok["supply_direction"]))
    if grok.get("x_sentiment"):
        parts.append(str(grok["x_sentiment"]))
    elif grok.get("volume_surge_reason"):
        parts.append(str(grok["volume_surge_reason"]))

    return vote, _one_comment(parts, "수급 지표 데이터 부족")


def _momentum_vote(ticker: str, stock: dict[str, Any], momentum: dict[str, Any]) -> tuple[str, list[str]]:
    key = normalize_ticker(ticker)
    m = (momentum.get("momentum_scores") or {}).get(key) or {}
    grok = _grok_momentum(ticker, momentum)
    mom_score = safe_float(m.get("momentum_score"), 50.0)
    vote = str(grok.get("vote") or m.get("grok_vote") or score_to_vote(mom_score))

    vol = safe_float(stock.get("volume_ratio"), 0.0)
    chg = safe_float(stock.get("change_rate"), 0.0)
    parts: list[str] = []

    pos = m.get("position_52w")
    if pos and pos != "N/A":
        parts.append(f"52주 {pos} 구간")

    parts.append(volume_flow_label(vol, chg))

    if m.get("trend"):
        parts.append(f"추세 {m['trend']}")

    if grok.get("momentum_direction"):
        parts.append(f"모멘텀 {grok['momentum_direction']}")
    if grok.get("position_52w_analysis"):
        parts.append(str(grok["position_52w_analysis"]))
    elif grok.get("x_buzz"):
        parts.append(f"X {grok['x_buzz']}")
    elif m.get("is_x_hot"):
        parts.append("X 화제 종목")

    return vote, _one_comment(parts, "모멘텀 데이터 부족")


def _fundamental_vote(ticker: str, stock: dict[str, Any], fundamental: dict[str, Any]) -> tuple[str, list[str]]:
    key = normalize_ticker(ticker)
    f = (fundamental.get("fundamental_scores") or {}).get(key) or {}

    per_v = stock.get("per")
    pbr_v = stock.get("pbr")
    if per_v is None or pbr_v is None:
        fin = get_kr_fundamentals(ticker)
        per_v = per_v if per_v is not None else fin.get("per")
        pbr_v = pbr_v if pbr_v is not None else fin.get("pbr")

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

    per = f.get("per")
    pbr = f.get("pbr")
    if (per in (None, "N/A") or pbr in (None, "N/A")) and per_v is not None and pbr_v is not None:
        per = f"{safe_float(per_v):.1f}"
        pbr = f"{safe_float(pbr_v):.1f}"

    parts: list[str] = []
    if per not in (None, "N/A") and pbr not in (None, "N/A"):
        parts.append(f"PER {per}, PBR {pbr}")
    elif per not in (None, "N/A"):
        parts.append(f"PER {per}")
    elif pbr not in (None, "N/A"):
        parts.append(f"PBR {pbr}")

    if f.get("comment") and f.get("comment") != "N/A":
        parts.append(str(f["comment"]))
    elif valuation != "N/A":
        parts.append(f"밸류 {valuation}")

    fallback = "펀더멘털 데이터 부족" if not parts else "N/A"
    return vote, _one_comment(parts, fallback)


def _risk_vote(ticker: str, risk: dict[str, Any], stock: dict[str, Any]) -> tuple[str, list[str]]:
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
            return "매도", _one_comment([f"52주 고점 근접, 손절 {stop}"], "추격매수 주의")
        if dist is not None and dist < -15:
            return "매수", _one_comment([f"조정 구간, 손절 {stop}"], "리스크 관망")
        return "홀드", _one_comment([f"손절선 {stop}"], "리스크 데이터 제한적")

    vote = str(r.get("final_verdict", "홀드"))
    sl = str(r.get("stop_loss") or "")
    if sl in ("", "N/A", "n/a") or "원" not in sl:
        sl = stop

    parts = [
        truncate_comment(r.get("risk_comment") or ""),
        truncate_comment(r.get("verdict_comment") or ""),
        f"손절선 {sl}" if sl != "N/A" else "",
    ]
    return vote, _one_comment(parts, f"손절선 {stop}")


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
        return "홀드", _one_comment([summary], "의견 없음")

    pipe_stock = _find_supply_stock(pipeline, ticker) or _find_watchlist_stock(pipeline, ticker) or stock_hint
    pipe_stock = _enrich_stock_metrics(pipe_stock, ticker)

    if agent_key == "macro":
        return _macro_vote(pipe_stock, pipeline.get("macro") or {})
    if agent_key == "supply":
        return _supply_vote(ticker, pipe_stock, pipeline.get("supply") or {})
    if agent_key == "momentum":
        return _momentum_vote(ticker, pipe_stock, pipeline.get("momentum") or {})
    if agent_key == "fundamental":
        return _fundamental_vote(ticker, pipe_stock, pipeline.get("fundamental") or {})
    if agent_key == "risk":
        return _risk_vote(ticker, pipeline.get("risk") or {}, pipe_stock)

    return "홀드", ["알 수 없는 에이전트"]
