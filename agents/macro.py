"""Stage 1: Macro analyst (Michael Chen)."""

from __future__ import annotations

import json
from typing import Any

import config
from data.kis_client import get_sector_trading_value
from utils.retry import retry

from .common import indicator_change_pct, normalize_phase, safe_float


def _sector_inflow_outflow() -> tuple[list[str], list[str]]:
    sectors = get_sector_trading_value() or []
    if not sectors:
        return [], []
    sorted_rows = sorted(sectors, key=lambda x: safe_float(x.get("change_rate"), 0.0), reverse=True)
    mid = max(1, len(sorted_rows) // 3)
    inflow = [str(s["name"]) for s in sorted_rows[:mid] if s.get("name")]
    outflow = [str(s["name"]) for s in sorted_rows[-mid:] if s.get("name")]
    return inflow, outflow


def _macro_comments(indicators: dict[str, Any]) -> dict[str, str]:
    comments: dict[str, str] = {}
    dollar = indicators.get("dollar_index") or {}
    rate = indicators.get("us10y") or {}
    vix = indicators.get("vix") or {}
    wti = indicators.get("wti") or {}
    copper = indicators.get("copper") or {}

    d_chg = indicator_change_pct(dollar if isinstance(dollar, dict) else None)
    if d_chg is None:
        comments["dollar"] = "N/A"
    elif d_chg > 0:
        comments["dollar"] = "달러 강세, 신흥국 부담"
    else:
        comments["dollar"] = "달러 약세, 신흥국 유리"

    r_chg = indicator_change_pct(rate if isinstance(rate, dict) else None)
    if r_chg is None:
        comments["rate"] = "N/A"
    elif r_chg > 0:
        comments["rate"] = "금리 상승, 주식 부담"
    else:
        comments["rate"] = "금리 하락, 주식 호재"

    vix_val = safe_float(str((vix or {}).get("value", "")).replace(",", ""), -1.0)
    if vix_val < 0:
        comments["vix"] = "N/A"
    elif vix_val >= 20:
        comments["vix"] = "시장 불안, 변동성 확대"
    else:
        comments["vix"] = "공포 완화, 시장 안정"

    w_chg = indicator_change_pct(wti if isinstance(wti, dict) else None)
    if w_chg is None:
        comments["wti"] = "N/A"
    elif w_chg > 0:
        comments["wti"] = "유가 상승, 인플레이션 우려"
    else:
        comments["wti"] = "경기 둔화 우려, 수요 감소"

    c_chg = indicator_change_pct(copper if isinstance(copper, dict) else None)
    if c_chg is None:
        comments["copper"] = "N/A"
    elif c_chg > 0:
        comments["copper"] = "구리 상승, 경기 회복 기대"
    else:
        comments["copper"] = "소폭 하락, 경기 중립"

    return comments


def _watchlist_verdict(favorable: list[str], unfavorable: list[str]) -> dict[str, str]:
    from .watchlist_data import KR_THEME_SECTORS, US_THEME_KEYWORDS

    def _kr_msg() -> str:
        if not favorable and not unfavorable:
            return "N/A"
        hits = [t for t, secs in KR_THEME_SECTORS.items() if any(s in favorable for s in secs)]
        bad = [t for t, secs in KR_THEME_SECTORS.items() if any(s in unfavorable for s in secs)]
        if hits and not bad:
            return f"{', '.join(hits[:2])} 등 관심 섹터에 우호적 환경"
        if bad and not hits:
            return "관심 섹터 전반 불리한 환경"
        return "관심 섹터 혼조, 선별 접근 필요"

    def _us_msg() -> str:
        if not favorable:
            return "N/A"
        hits = [
            t
            for t, keys in US_THEME_KEYWORDS.items()
            if any(any(k in f or f in k for k in keys) for f in favorable)
        ]
        if hits:
            return f"{', '.join(hits[:2])} 등 관심 테마에 유리한 환경"
        return "관심 테마와 유입 섹터 불일치, 선별 필요"

    return {"KR": _kr_msg(), "US": _us_msg()}


def _determine_phase(indices: dict[str, Any], indicators: dict[str, Any]) -> tuple[str, str]:
    down = 0
    up = 0
    total = 0
    for key in ("KOSPI", "KOSDAQ", "S&P500", "NASDAQ"):
        row = indices.get(key) or indices.get(key.replace("S&P500", "S&P500"))
        if not isinstance(row, dict):
            continue
        chg = indicator_change_pct(row)
        if chg is None:
            continue
        total += 1
        if chg < -0.5:
            down += 1
        elif chg > 0.5:
            up += 1

    vix_row = indicators.get("vix") or {}
    vix_val = safe_float(str(vix_row.get("value", "")).replace(",", ""), -1.0)

    if (vix_val >= 20 and vix_val > 0) or (total and down >= max(2, total - 1)):
        return "위험회피", "지수 약세와 변동성 지표가 보수적 대응을 요구합니다."
    if total and up >= max(2, total - 1) and (vix_val < 20 or vix_val < 0):
        return "강세", "주요 지수 상승과 변동성 안정이 위험자산에 우호적입니다."
    return "중립", "지수·변동성 신호가 엇갈려 방향성이 뚜렷하지 않습니다."


def analyze_macro(
    indices: dict[str, Any],
    indicators: dict[str, Any],
    sector_flow: list[dict[str, Any]] | None = None,
    news: str = "",
    logger: Any = None,
) -> dict[str, Any]:
    """Stage 1 macro analysis (rule-based; optional Gemini polish)."""
    del news  # reserved
    inflow, outflow = _sector_inflow_outflow()
    if sector_flow:
        etf_in = [str(s.get("sector", "")) for s in sector_flow if s.get("flow") == "유입"][:5]
        etf_out = [str(s.get("sector", "")) for s in sector_flow if s.get("flow") == "유출"][:5]
        if etf_in:
            inflow = list(dict.fromkeys(inflow + etf_in))[:8]
        if etf_out:
            outflow = list(dict.fromkeys(outflow + etf_out))[:8]

    phase, reason = _determine_phase(indices, indicators)
    comments = _macro_comments(indicators)
    favorable = inflow[:5]
    unfavorable = outflow[:5]
    result = {
        "market_phase": phase,
        "market_phase_reason": reason,
        "macro_comments": comments,
        "favorable_sectors": favorable,
        "unfavorable_sectors": unfavorable,
        "watchlist_verdict": _watchlist_verdict(favorable, unfavorable),
        "sector_rotation": {"flowing_in": favorable, "flowing_out": unfavorable},
        "meta": {"mode": "rules"},
    }

    if config.GEMINI_API_KEY:
        try:
            from .gemini_client import generate_gemini_json

            prompt = f"""
당신은 20년 경력의 글로벌 매크로 애널리스트 Michael Chen입니다.
감정적 표현 배제, 건조하고 객관적으로 작성.
위험회피/중립/강세 중 하나로 시장 국면 정의.
타겟 섹터에 미치는 영향 2문장 이내로 요약.
인사말·서론 없이 JSON만 반환.

아래 실데이터만 사용. 없는 수치는 N/A, 추측 금지.
기존 market_phase는 유지하거나 동의할 때만 수정: {phase}

[지수]{json.dumps(indices, ensure_ascii=False)[:2000]}
[지표]{json.dumps(indicators, ensure_ascii=False)[:2000]}
[섹터]{json.dumps({"유입": favorable, "유출": unfavorable}, ensure_ascii=False)}

스키마:
{{
  "market_phase":"위험회피/중립/강세",
  "market_phase_reason":"한줄",
  "macro_comments":{{"dollar":"","rate":"","vix":"","wti":"","copper":""}},
  "favorable_sectors":[],
  "unfavorable_sectors":[],
  "watchlist_verdict":{{"KR":"","US":""}}
}}
"""
            parsed = generate_gemini_json(prompt, agent="macro", logger=logger)
            if parsed:
                result["market_phase"] = normalize_phase(str(parsed.get("market_phase", phase)))
                result["market_phase_reason"] = str(
                    parsed.get("market_phase_reason") or result["market_phase_reason"]
                )
                if isinstance(parsed.get("macro_comments"), dict):
                    for k, v in parsed["macro_comments"].items():
                        if v and str(v) != "N/A":
                            result["macro_comments"][k] = str(v)
                if parsed.get("favorable_sectors"):
                    result["favorable_sectors"] = list(parsed["favorable_sectors"])
                if parsed.get("unfavorable_sectors"):
                    result["unfavorable_sectors"] = list(parsed["unfavorable_sectors"])
                if isinstance(parsed.get("watchlist_verdict"), dict):
                    result["watchlist_verdict"].update(parsed["watchlist_verdict"])
                result["meta"]["mode"] = "rules+gemini"
        except Exception:
            pass

    return result
