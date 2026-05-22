# -*- coding: utf-8 -*-
"""AI 쉬운 해설 — 최종 병합 종목의 plainReason/plainRisk/viewGuide 생성."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import ai_models
import config
from agents.mock_trading.models import (
    PLAIN_LANGUAGE_EDITOR_DISPLAY,
    PLAIN_LANGUAGE_EDITOR_KEY,
    PLAIN_LANGUAGE_EDITOR_MODEL,
)
from agents.mock_trading.plain_language import build_plain_copy

KST = ZoneInfo("Asia/Seoul")

_FORBIDDEN_PHRASES = (
    "무조건",
    "반드시 매수",
    "확실한 수익",
    "손절",
    "손절가",
    "자동 손절",
    "손실 시 종료",
)


def _aggregate_source_text(
    weekly_doc: dict[str, Any] | None,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    reasons: dict[str, list[str]] = defaultdict(list)
    risks: dict[str, list[str]] = defaultdict(list)
    for agent in (weekly_doc or {}).get("agents") or []:
        for rec in agent.get("recommendations") or []:
            if not isinstance(rec, dict):
                continue
            ticker = str(rec.get("ticker", "")).zfill(6)
            if not ticker:
                continue
            for r in rec.get("reasons") or []:
                s = str(r).strip()
                if s and s not in reasons[ticker]:
                    reasons[ticker].append(s)
            for rf in rec.get("risk_factors") or []:
                s = str(rf).strip()
                if s and s not in risks[ticker]:
                    risks[ticker].append(s)
    return reasons, risks


def _card_input_payload(
    card: dict[str, Any],
    *,
    reason_map: dict[str, list[str]],
    risk_map: dict[str, list[str]],
) -> dict[str, Any]:
    ticker = str(card.get("ticker", "")).zfill(6)
    grok = card.get("grok_validation") if isinstance(card.get("grok_validation"), dict) else {}
    return {
        "ticker": ticker,
        "name": card.get("name"),
        "target_price": card.get("target_price"),
        "entry_price": card.get("entry_price"),
        "entry_range": card.get("entry_range"),
        "recommending_agents": card.get("recommending_agents") or [],
        "consensus_label": card.get("consensus_label"),
        "original_reasons": (reason_map.get(ticker) or [])
        + list(card.get("reasons_sample") or []),
        "original_risk_factors": (risk_map.get(ticker) or []),
        "grok_summary": grok.get("summary"),
        "grok_positive_signals": grok.get("positive_signals") or [],
        "grok_warning_signals": grok.get("warning_signals") or [],
    }


def _build_prompt(cards_payload: list[dict[str, Any]]) -> str:
    return f"""당신은 '{PLAIN_LANGUAGE_EDITOR_DISPLAY}' 편집 에이전트입니다.
역할: 아래 최종 추천 종목의 원문 분석을 초보 투자자도 이해하는 짧은 한국어로 바꿉니다.

절대 금지:
- 종목 추가/삭제, 추천 순위·목표가·진입가 변경
- 손절·자동 매도·손실 종료 관련 문구
- "무조건 오른다", "지금 반드시 매수", "확실한 수익" 등 확신 표현
- 수급, 모멘텀, 오버행, 리레이팅, 밸류에이션, 컨센서스, 변동성 확대 등 전문 용어 그대로 사용 (필요 시 쉬운 말로 풀기)

작성 규칙:
- plainReason: 왜 사람들이 관심 가질 수 있는지 1~2문장 (일상적 한국어, ~어요 체)
- plainRisk: 지금 샀을 때 가격이 내려갈 수 있는 이유 1~2문장 (원문 위험 약화·누락 금지)
- viewGuide: 장중 무엇을 보며 관찰할지 1문장 (매수 확정 아님)

입력 종목 JSON:
{json.dumps(cards_payload, ensure_ascii=False)}

반드시 아래 JSON만 출력:
{{
  "cards": [
    {{
      "ticker": "6자리",
      "plainReason": "쉬운 말 1~2문장",
      "plainRisk": "쉬운 말 1~2문장",
      "viewGuide": "관찰 안내 1문장"
    }}
  ]
}}
입력과 동일한 ticker {len(cards_payload)}개 전부 포함. 다른 필드 출력 금지.
"""


def _sanitize_field(text: str) -> str:
    s = str(text or "").strip()
    for bad in _FORBIDDEN_PHRASES:
        s = s.replace(bad, "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _validate_plain_row(row: dict[str, Any], ticker: str) -> dict[str, str] | None:
    if str(row.get("ticker", "")).zfill(6) != ticker:
        return None
    pr = _sanitize_field(row.get("plainReason"))
    pk = _sanitize_field(row.get("plainRisk"))
    vg = _sanitize_field(row.get("viewGuide"))
    if len(pr) < 12 or len(pk) < 12 or len(vg) < 10:
        return None
    return {"plainReason": pr, "plainRisk": pk, "viewGuide": vg}


def _fallback_plain(
    card: dict[str, Any],
    reason_map: dict[str, list[str]],
    risk_map: dict[str, list[str]],
) -> dict[str, str]:
    ticker = str(card.get("ticker", "")).zfill(6)
    plain = build_plain_copy(
        name=str(card.get("name") or ""),
        reason_lines=(reason_map.get(ticker) or []) + list(card.get("reasons_sample") or []),
        risk_lines=risk_map.get(ticker) or [],
        grok_validation=card.get("grok_validation"),
    )
    return {
        "plainReason": plain["plainReason"],
        "plainRisk": plain["plainRisk"],
        "viewGuide": plain["viewGuide"],
    }


def _apply_plain_to_cards(
    merged_cards: list[dict[str, Any]],
    plain_by_ticker: dict[str, dict[str, str]],
    *,
    reason_map: dict[str, list[str]],
    risk_map: dict[str, list[str]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for card in merged_cards:
        row = dict(card)
        ticker = str(row.get("ticker", "")).zfill(6)
        plain = plain_by_ticker.get(ticker) or _fallback_plain(row, reason_map, risk_map)
        row["plainReason"] = plain["plainReason"]
        row["plainRisk"] = plain["plainRisk"]
        row["viewGuide"] = plain["viewGuide"]
        row["plain_language_editor"] = {
            "agent_key": PLAIN_LANGUAGE_EDITOR_KEY,
            "display_name": PLAIN_LANGUAGE_EDITOR_DISPLAY,
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "source": plain_by_ticker.get(ticker, {}).get("_source", "fallback"),
        }
        out.append(row)
    return out


def run_plain_language_editor(
    merged_doc: dict[str, Any],
    weekly_doc: dict[str, Any] | None = None,
    *,
    model_id: str | None = None,
) -> dict[str, Any]:
    """
    merged_doc의 merged_cards에 plain 필드 추가.
    추천 종목·가격·순위는 변경하지 않음.
    """
    cards = list(merged_doc.get("merged_cards") or [])
    if not cards:
        return {
            **merged_doc,
            "plain_language_editor": {
                "agent_key": PLAIN_LANGUAGE_EDITOR_KEY,
                "error": "merged_cards empty",
                "ok": False,
            },
        }

    reason_map, risk_map = _aggregate_source_text(weekly_doc)
    payloads = [_card_input_payload(c, reason_map=reason_map, risk_map=risk_map) for c in cards]

    model = model_id or PLAIN_LANGUAGE_EDITOR_MODEL
    meta: dict[str, Any] = {
        "agent_key": PLAIN_LANGUAGE_EDITOR_KEY,
        "display_name": PLAIN_LANGUAGE_EDITOR_DISPLAY,
        "model_id": model,
        "ok": False,
        "error": None,
        "card_count": len(cards),
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
    }

    plain_by_ticker: dict[str, dict[str, str]] = {}

    if not config.GEMINI_API_KEY:
        meta["error"] = "GEMINI_API_KEY 미설정"
        for c in cards:
            t = str(c.get("ticker", "")).zfill(6)
            fb = _fallback_plain(c, reason_map, risk_map)
            fb["_source"] = "rule_fallback"
            plain_by_ticker[t] = fb
    else:
        from agents.gemini_client import generate_gemini_json

        parsed = generate_gemini_json(
            _build_prompt(payloads),
            agent=f"mock_trading_{PLAIN_LANGUAGE_EDITOR_KEY}",
            model=model,
            tier=ai_models.ModelTier.SUMMARY,
        )
        rows = (parsed or {}).get("cards") if isinstance(parsed, dict) else None
        if not isinstance(rows, list):
            meta["error"] = "gemini_json_parse_failed"
            for c in cards:
                t = str(c.get("ticker", "")).zfill(6)
                fb = _fallback_plain(c, reason_map, risk_map)
                fb["_source"] = "rule_fallback"
                plain_by_ticker[t] = fb
        else:
            for c in cards:
                t = str(c.get("ticker", "")).zfill(6)
                matched = None
                for row in rows:
                    if isinstance(row, dict):
                        validated = _validate_plain_row(row, t)
                        if validated:
                            matched = validated
                            break
                if matched:
                    matched["_source"] = "gemini"
                    plain_by_ticker[t] = matched
                else:
                    fb = _fallback_plain(c, reason_map, risk_map)
                    fb["_source"] = "rule_fallback"
                    plain_by_ticker[t] = fb
            gemini_ok = sum(1 for v in plain_by_ticker.values() if v.get("_source") == "gemini")
            meta["ok"] = gemini_ok > 0
            meta["gemini_cards"] = gemini_ok
            meta["fallback_cards"] = len(cards) - gemini_ok
            if gemini_ok == 0:
                meta["error"] = "all_cards_fallback"

    updated_cards = _apply_plain_to_cards(
        cards, plain_by_ticker, reason_map=reason_map, risk_map=risk_map
    )

    return {
        **merged_doc,
        "merged_cards": updated_cards,
        "plain_language_editor": meta,
    }
