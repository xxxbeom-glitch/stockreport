"""Per-stock AI label voting — API first, rules fallback (KR MVP, 2 labels)."""

from __future__ import annotations

from typing import Any, TypedDict

from .label_rules import (
    LABEL_REGRET,
    LABEL_TIMING,
    label_to_badge_class,
    normalize_label,
    reason_to_lines,
    sanitize_label_reason,
)
from .label_vote_api import api_vote_deepseek, api_vote_gemini, api_vote_grok
from .label_vote_helpers import enrich_stock_metrics, normalize_ticker


class AiVoteRecord(TypedDict, total=False):
    engine: str
    model: str
    label: str
    reason: str
    confidence: int
    source: str


class StockLabelVoteResult(TypedDict):
    ticker: str
    name: str
    ai_votes: list[AiVoteRecord]
    final_label: str
    label_reason: str
    label_reason_lines: list[str]
    verdict_class: str
    vote_summary: str
    vote_sources: dict[str, str]


def resolve_final_label(
    deepseek: AiVoteRecord,
    grok: AiVoteRecord,
    gemini: AiVoteRecord,
) -> tuple[str, str]:
    """
    2-label merge:
    - 과열/리스크 2표 이상 → 지금 사기엔 좀...
    - 그 외 데이터 2표 이상 → 안 사면 후회함
    - Gemini 보수 검수 tie-break
    """
    votes = [deepseek, grok, gemini]
    labels = [normalize_label(v.get("label")) for v in votes]
    timing_n = sum(1 for lb in labels if lb == LABEL_TIMING)
    regret_n = sum(1 for lb in labels if lb == LABEL_REGRET)

    if timing_n >= 2:
        final = LABEL_TIMING
    elif regret_n >= 2:
        final = LABEL_REGRET
    else:
        final = normalize_label(gemini.get("label"))

    reason_parts: list[str] = []
    for v in votes:
        if normalize_label(v.get("label")) == final and v.get("reason"):
            reason_parts.append(str(v["reason"]))
    if len(reason_parts) < 2:
        for v in votes:
            if v.get("reason") and str(v["reason"]) not in reason_parts:
                reason_parts.append(str(v["reason"]))
            if len(reason_parts) >= 2:
                break
    merged = sanitize_label_reason(" ".join(reason_parts))
    if not merged:
        merged = sanitize_label_reason(str(deepseek.get("reason", "")))
    return final, merged


def build_stock_label_votes(
    ticker: str,
    name: str,
    stock: dict[str, Any],
    pipeline: dict[str, Any] | None,
    *,
    logger: Any = None,
) -> StockLabelVoteResult:
    """Run per-stock DeepSeek → Grok → Gemini vote (API or rules)."""
    pipe = pipeline or {}
    row = enrich_stock_metrics(dict(stock), ticker)

    deepseek = api_vote_deepseek(row, pipe, logger=logger)
    grok = api_vote_grok(row, pipe, logger=logger)
    gemini = api_vote_gemini(row, pipe, logger=logger)

    final_label, label_reason = resolve_final_label(deepseek, grok, gemini)
    ai_votes: list[AiVoteRecord] = [deepseek, grok, gemini]
    lines = reason_to_lines(label_reason)
    summary_parts = [
        f"{v['engine']}({v.get('source', '?')}): {v['label']}" for v in ai_votes
    ]

    return {
        "ticker": normalize_ticker(ticker),
        "name": name,
        "ai_votes": ai_votes,
        "final_label": final_label,
        "label_reason": label_reason,
        "label_reason_lines": lines,
        "verdict_class": label_to_badge_class(final_label),
        "vote_summary": " · ".join(summary_parts),
        "vote_sources": {
            "DeepSeek": str(deepseek.get("source", "rules")),
            "Grok": str(grok.get("source", "rules")),
            "Gemini": str(gemini.get("source", "rules")),
        },
    }


def ai_votes_for_template(votes: list[AiVoteRecord]) -> list[dict[str, Any]]:
    """Optional template shape (kr_market UI hides list; reportData keeps detail)."""
    rows: list[dict[str, Any]] = []
    for v in votes:
        engine = str(v.get("engine", ""))
        label = normalize_label(v.get("label"))
        rows.append(
            {
                "name": engine,
                "title": engine,
                "engine": engine,
                "model": v.get("model", ""),
                "label": label,
                "vote": label,
                "confidence": v.get("confidence", 0),
                "source": v.get("source", "rules"),
                "reason": reason_to_lines(str(v.get("reason", ""))) or [str(v.get("reason", ""))],
                "vote_class": label_to_badge_class(label),
            }
        )
    return rows


def build_pipeline_stock_labels(
    pipeline: dict[str, Any],
    *,
    stocks: list[dict[str, Any]] | None = None,
    logger: Any = None,
) -> dict[str, StockLabelVoteResult]:
    """Batch label votes keyed by normalized ticker."""
    wl = stocks or (pipeline.get("watchlist_data") or {}).get("stocks") or []
    out: dict[str, StockLabelVoteResult] = {}
    for s in wl:
        ticker = str(s.get("ticker", ""))
        if not ticker:
            continue
        key = normalize_ticker(ticker)
        out[key] = build_stock_label_votes(
            ticker, str(s.get("name", ticker)), s, pipeline, logger=logger
        )
    pipeline.setdefault("label_votes", out)
    return out
