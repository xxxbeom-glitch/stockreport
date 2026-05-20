"""Rules-based label votes (fallback when API unavailable)."""

from __future__ import annotations

from typing import Any

import ai_models

from .common import distance_from_high_pct, safe_float
from .label_rules import LABEL_REGRET, LABEL_TIMING, normalize_label, sanitize_label_reason
from .label_vote_helpers import enrich_stock_metrics, grok_momentum_verdict, grok_supply_verdict, normalize_ticker


def _record(
    engine: str,
    model: str,
    label: str,
    reason: str,
    *,
    confidence: int = 55,
) -> dict[str, Any]:
    return {
        "engine": engine,
        "model": model,
        "label": normalize_label(label),
        "reason": sanitize_label_reason(reason),
        "confidence": max(0, min(100, int(confidence))),
        "source": "rules",
    }


def rules_vote_deepseek(stock: dict[str, Any], pipeline: dict[str, Any]) -> dict[str, Any]:
    ticker = normalize_ticker(str(stock.get("ticker", "")))
    fundamental = (pipeline.get("fundamental") or {}).get("fundamental_scores") or {}
    f = fundamental.get(ticker) or {}
    fs = safe_float(f.get("fundamental_score"), 50.0)
    supply_score = safe_float(stock.get("score"), 0.0)
    foreign = safe_float(stock.get("foreign_net"), 0.0)
    valuation = str(f.get("valuation", ""))

    if fs >= 60 and supply_score >= 65 and foreign > 0:
        label, reason, conf = LABEL_REGRET, "수급·펀더멘털 점수가 동시에 우호적.", 72
    elif valuation == "고평가" or fs < 45 or supply_score < 45:
        label, reason, conf = LABEL_TIMING, "밸류·수급 점수 기준 진입 부담.", 68
    elif fs >= 52 and supply_score >= 55:
        label, reason, conf = LABEL_REGRET, "데이터상 재료는 붙었으나 변동성 확인 필요.", 62
    else:
        label, reason, conf = LABEL_TIMING, "지표가 엇갈려 방향 확인이 어려움.", 50

    if f.get("comment"):
        reason = str(f["comment"])[:200]

    return _record("DeepSeek", ai_models.DEEPSEEK_VOTE_MODEL, label, reason, confidence=conf)


def rules_vote_grok(stock: dict[str, Any], pipeline: dict[str, Any]) -> dict[str, Any]:
    ticker = str(stock.get("ticker", ""))
    supply = pipeline.get("supply") or {}
    momentum = pipeline.get("momentum") or {}
    g_s = grok_supply_verdict(ticker, supply)
    g_m = grok_momentum_verdict(ticker, momentum)

    vote = str(g_s.get("vote") or stock.get("grok_vote") or g_m.get("vote") or "")
    is_hot = bool(g_m.get("is_x_hot") or g_s.get("is_x_hot"))
    vol = safe_float(stock.get("volume_ratio"), 0.0)
    chg = safe_float(stock.get("change_rate"), 0.0)

    if is_hot and (chg > 5 or vol >= 3):
        label, reason, conf = LABEL_TIMING, "언급량 증가와 단기 과열 신호.", 70
    elif vote == "매도" or chg > 8:
        label, reason, conf = LABEL_TIMING, "시장 반응이 과열된 구간.", 68
    elif vote == "매수":
        label, reason, conf = LABEL_REGRET, "시장 관심은 붙었으나 추격 부담 존재.", 58
    else:
        label, reason, conf = LABEL_TIMING, "X·수급 심리가 뚜렷하지 않음.", 48

    comment = g_s.get("comment") or g_m.get("comment")
    if comment:
        reason = str(comment)[:200]

    return _record("Grok", ai_models.GROK_VOTE_MODEL, label, reason, confidence=conf)


def rules_vote_gemini(stock: dict[str, Any], pipeline: dict[str, Any]) -> dict[str, Any]:
    ticker = normalize_ticker(str(stock.get("ticker", "")))
    risk = pipeline.get("risk") or {}
    r = (risk.get("risk_assessments") or {}).get(ticker) or {}
    phase = str((pipeline.get("macro") or {}).get("market_phase", "중립"))

    verdict = str(r.get("final_verdict", "홀드"))
    dist = distance_from_high_pct(stock.get("price"), stock.get("high_52"))
    risk_level = str(r.get("risk_level", "보통"))

    if verdict == "매도" or risk_level == "높음" or (dist is not None and dist > -3):
        label, reason, conf = LABEL_TIMING, "리스크·고점 부담이 큼.", 75
    elif verdict == "매수" and phase != "위험회피" and risk_level == "낮음":
        label, reason, conf = LABEL_REGRET, "리스크 대비 재료는 유효.", 65
    elif phase == "위험회피":
        label, reason, conf = LABEL_TIMING, "시장 국면상 보수 접근 필요.", 72
    else:
        label, reason, conf = LABEL_TIMING, "리스크·타이밍 신호 혼재.", 55

    if r.get("comment"):
        reason = str(r["comment"])[:200]

    return _record("Gemini", ai_models.GEMINI_RISK_MODEL, label, reason, confidence=conf)
