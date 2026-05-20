"""Stage 2: Supply/demand analyst (James Park) — Grok + X real-time search."""

from __future__ import annotations

import json
from typing import Any

import config
from data.kr_market import get_stock_snapshot

from .common import ANALYST_VOICE_RULES, format_analyst_comment, normalize_phase, safe_float
from .watchlist_data import KR_THEME_SECTORS, US_THEME_KEYWORDS, build_watchlist_data


def _theme_matches_favorable(theme: str, market: str, favorable: list[str]) -> bool:
    if not favorable:
        return True
    if market == "KR":
        sectors = KR_THEME_SECTORS.get(theme, [])
        return any(s in favorable for s in sectors)
    keys = US_THEME_KEYWORDS.get(theme, [theme])
    return any(any(k in f or f in k for k in keys) for f in favorable)


def _supply_score(stock: dict[str, Any], in_favorable: bool) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []

    foreign = stock.get("foreign_net")
    if foreign is not None:
        fn = safe_float(foreign, 0.0)
        if fn > 0:
            score += 30
            reasons.append("외국인 순매수")
        elif fn < -5_000_000_000:
            reasons.append("외국인 대량 매도")

    strength = stock.get("conclusion_strength")
    if strength is not None:
        s = safe_float(strength, 0.0)
        if s >= 100:
            score += 20
            reasons.append(f"체결강도 {s:.0f}%")
        elif s < 90 and stock.get("market") == "KR":
            reasons.append(f"체결강도 {s:.0f}% 약세")

    vol = safe_float(stock.get("volume_ratio"), 0.0)
    if vol >= 2.0:
        score += 20
        reasons.append(f"거래량 {vol:.1f}배")

    if in_favorable:
        score += 30
        reasons.append("유입 섹터")

    return score, " + ".join(reasons) if reasons else "조건 미충족"


def _exclude_reason(stock: dict[str, Any], phase: str, in_favorable: bool) -> str | None:
    market = stock.get("market", "KR")
    if phase == "위험회피" and not in_favorable:
        return "유출 섹터 / 매크로 위험회피"

    foreign = stock.get("foreign_net")
    if foreign is not None:
        fn = safe_float(foreign, 0.0)
        if fn < -10_000_000_000:
            return "외국인 대량 매도"

    if market == "KR":
        strength = stock.get("conclusion_strength")
        if strength is not None and safe_float(strength, 100.0) < 90:
            return f"체결강도 {safe_float(strength):.0f}% (90% 미만)"

    return None


def _enrich_kr_stock(ticker: str, name: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load KIS/pykrx snapshot for a single KR ticker."""
    from data.kr_market import get_kr_fundamentals

    code = ticker.zfill(6)
    snap = get_stock_snapshot(code, market="KOSPI")
    fund = get_kr_fundamentals(code)
    row: dict[str, Any] = {
        "ticker": code,
        "name": name,
        "market": "KR",
        "theme": (extra or {}).get("theme", ""),
        "price": snap.get("price"),
        "change_rate": snap.get("change_rate"),
        "low_52": snap.get("low_52"),
        "high_52": snap.get("high_52"),
        "foreign_net": snap.get("foreign_net_buy"),
        "volume_ratio": (extra or {}).get("volume_ratio"),
        "conclusion_strength": (extra or {}).get("conclusion_strength"),
        "per": fund.get("per"),
        "pbr": fund.get("pbr"),
        "foreign_ownership": fund.get("foreign_ownership"),
    }
    if extra:
        row.update({k: v for k, v in extra.items() if k not in row or row[k] is None})
    return row


def _explicit_stocks_from_market_data(market_data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Build stock rows when caller passes market_data['stocks'] (e.g. code/name only)."""
    raw = market_data.get("stocks")
    if not isinstance(raw, list) or not raw:
        return None

    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or item.get("code") or "").strip()
        if not ticker:
            continue
        name = str(item.get("name") or ticker)
        market = str(item.get("market") or ("KR" if ticker.isdigit() else "US")).upper()

        if market == "KR":
            rows.append(_enrich_kr_stock(ticker, name, item))
        else:
            rows.append(
                {
                    "ticker": ticker.upper(),
                    "name": name,
                    "market": "US",
                    "theme": item.get("theme", ""),
                    **{k: v for k, v in item.items() if k not in ("code",)},
                }
            )
    return rows or None


def _macro_from_market_data(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    if market_data.get("indices") or market_data.get("market_indicators"):
        from .macro import analyze_macro

        return analyze_macro(
            indices=market_data.get("indices") or {},
            indicators=market_data.get("market_indicators") or market_data.get("indicators") or {},
            sector_flow=market_data.get("sector_flow") or [],
            logger=logger,
        )
    return {
        "market_phase": "중립",
        "market_phase_reason": "매크로 데이터 없음",
        "favorable_sectors": [],
        "unfavorable_sectors": [],
        "meta": {"mode": "neutral-default"},
    }


def _grok_supply_analysis(
    stocks: list[dict[str, Any]],
    macro_result: dict[str, Any],
    market_data: dict[str, Any],
    logger: Any = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Grok + x_search: X 수급 분위기, 외국인/기관, 거래량, 매수/홀드/매도."""
    if not config.GROK_API_KEY or not stocks:
        return None, {"mode": "disabled", "x_search_enabled": False}

    from .grok_client import grok_x_search_json

    stock_lines = [
        f"- {s.get('name')}({s.get('ticker')}): 가격={s.get('price')}, 등락={s.get('change_rate')}%, "
        f"거래량배수={s.get('volume_ratio')}, 외국인순매수={s.get('foreign_net')}, 체결강도={s.get('conclusion_strength')}"
        for s in stocks[:8]
    ]

    prompt = f"""
당신은 기관·외국인 수급을 읽는 애널리스트 James Park입니다.
가격·52주·모멘텀은 다루지 말고, 외국인 순매수·체결강도·거래량·X 심리만 해석하세요.
{ANALYST_VOICE_RULES}

예시 (James Park 톤):
"외국인이 오늘 38억원어치 사들였어요. 거래량도 평균의 91배나 터졌고요. 큰손들이 조용히 담고 있는 신호예요."

반드시 X(트위터) 실시간 검색(x_search) 결과를 사용. 추측·과거 학습만으로 답하지 마.

[시장 국면] {macro_result.get("market_phase")} — {macro_result.get("market_phase_reason", "")}
[유입 섹터] {macro_result.get("favorable_sectors", [])[:5]}
[분석 종목]
{chr(10).join(stock_lines)}

[추가 시장 데이터]
{json.dumps(market_data, ensure_ascii=False)[:2000]}

각 종목마다 vote(매수/홀드/매도)와 comment(수급 해석 3문장)를 작성하세요.

JSON만 반환:
{{
  "summary": "전체 수급 3문장 요약",
  "sector_flow": {{"유입": [], "유출": []}},
  "verdicts": {{
    "티커": {{
      "name": "종목명",
      "vote": "매수",
      "comment": "외국인·체결강도·거래량을 해석한 3문장"
    }}
  }}
}}
"""
    return grok_x_search_json(
        prompt, agent="supply_demand", logger=logger, model=config.GROK_VOTE_MODEL
    )


def _merge_grok_supply(rules: dict[str, Any], grok: dict[str, Any] | None) -> None:
    if not grok:
        return

    if grok.get("summary"):
        rules["summary"] = str(grok["summary"])
        rules["x_supply_buzz"] = str(grok["summary"])
    if isinstance(grok.get("sector_flow"), dict):
        rules["sector_flow_x"] = grok["sector_flow"]

    verdicts = grok.get("verdicts") or {}
    rules["grok_verdicts"] = verdicts

    by_ticker = {str(s.get("ticker")): s for s in rules.get("filtered_stocks", [])}
    for key, v in verdicts.items():
        if not isinstance(v, dict):
            continue
        ticker = str(key)
        stock = by_ticker.get(ticker) or by_ticker.get(ticker.zfill(6))
        if not stock:
            continue
        stock["grok_vote"] = v.get("vote")
        if v.get("comment"):
            stock["supply_comment"] = format_analyst_comment(v["comment"])
        elif v.get("x_sentiment") or v.get("supply_direction"):
            merged = " ".join(
                str(x)
                for x in (
                    v.get("supply_direction"),
                    v.get("x_sentiment"),
                    v.get("volume_surge_reason"),
                )
                if x
            )
            stock["supply_comment"] = format_analyst_comment(merged)


def analyze_supply(
    macro_result: dict[str, Any], watchlist_data: dict[str, Any], logger: Any = None
) -> dict[str, Any]:
    """Filter watchlist by macro phase and supply metrics; enrich with Grok."""
    phase = normalize_phase(str(macro_result.get("market_phase", "중립")))
    favorable = [str(s) for s in macro_result.get("favorable_sectors", [])]
    unfavorable = [str(s) for s in macro_result.get("unfavorable_sectors", [])]

    filtered: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for stock in watchlist_data.get("stocks", []):
        theme = str(stock.get("theme", ""))
        market = str(stock.get("market", "KR"))
        in_fav = _theme_matches_favorable(theme, market, favorable) if phase == "위험회피" else True

        if any(
            s in unfavorable
            for s in (KR_THEME_SECTORS.get(theme, []) if market == "KR" else US_THEME_KEYWORDS.get(theme, [theme]))
        ):
            in_fav = False

        reason_out = _exclude_reason(stock, phase, in_fav)
        if reason_out:
            excluded.append(
                {"ticker": stock.get("ticker"), "name": stock.get("name"), "reason": reason_out}
            )
            continue

        score, reason = _supply_score(stock, in_fav)
        if score < 40 and phase == "위험회피":
            excluded.append(
                {
                    "ticker": stock.get("ticker"),
                    "name": stock.get("name"),
                    "reason": reason or "수급 점수 부족",
                }
            )
            continue

        filtered.append(
            {
                "ticker": stock.get("ticker"),
                "name": stock.get("name"),
                "market": market,
                "theme": theme,
                "reason": reason,
                "score": score,
                **{k: stock.get(k) for k in stock if k not in {"ticker", "name", "market", "theme"}},
            }
        )

    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)

    result: dict[str, Any] = {
        "market_phase": phase,
        "filtered_stocks": filtered,
        "excluded_stocks": excluded,
        "x_supply_buzz": "N/A",
        "grok_verdicts": {},
        "meta": {"mode": "rules", "x_search_enabled": False},
    }

    grok_targets = filtered if filtered else list(watchlist_data.get("stocks", []))[:8]
    grok_parsed, grok_meta = _grok_supply_analysis(
        grok_targets,
        macro_result,
        watchlist_data,
        logger=logger,
    )
    result["meta"] = {**result["meta"], **grok_meta}
    if grok_meta.get("x_search_enabled"):
        result["meta"]["mode"] = "rules+grok+x_search"
    _merge_grok_supply(result, grok_parsed)

    return result


def analyze_supply_demand(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """Run macro + supply; supports market_data['stocks'] with code/name for direct analysis."""
    explicit = _explicit_stocks_from_market_data(market_data)
    macro = _macro_from_market_data(market_data, logger=logger)

    if explicit is not None:
        watchlist = {
            "stocks": explicit,
            "total_scanned": len(explicit),
            "indices": market_data.get("indices") or {},
            "indicators": market_data.get("market_indicators") or {},
            "sector_flow": market_data.get("sector_flow") or [],
        }
    else:
        watchlist = build_watchlist_data(market_data)

    return analyze_supply(macro, watchlist, logger=logger)
