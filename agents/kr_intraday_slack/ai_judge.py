"""WatchlistPick → LLM 판단 → SlackMessage (AI 필수)."""

from __future__ import annotations

import json
import logging
from typing import Any

from .constants import (
    SCAN_SLOTS,
    SLACK_SEND_ALLOWED,
    SLACK_SEND_FORBIDDEN,
    normalize_decision,
)
from .llm_client import call_llm_json, is_ai_configured
from .slack_message import build_slack_message_from_ai

logger = logging.getLogger("kr_intraday.ai_judge")

RULE_CANDIDATE_MIN = 3
RULE_CANDIDATE_MAX = 7


def _fmt_range(low: Any, high: Any) -> str:
    try:
        lo = int(low)
        hi = int(high)
        if lo > 0 and hi > 0:
            return f"{lo:,}원 ~ {hi:,}원"
    except (TypeError, ValueError):
        pass
    return ""


def _resolve_entry_range(
    candidate: dict[str, Any], item: dict[str, Any]
) -> tuple[str, int | None, int | None]:
    """
    AI entry_price_range는 current_price(원)와 동일 단위여야 함.
    범위가 현재가 대비 비정상(×10·÷10 등)이면 규칙 기반 entry_range로 대체.
    """
    rule_range = str(candidate.get("entry_range") or "")
    rule_low = candidate.get("entry_low")
    rule_high = candidate.get("entry_high")
    try:
        rule_lo = int(rule_low) if rule_low is not None else 0
        rule_hi = int(rule_high) if rule_high is not None else 0
    except (TypeError, ValueError):
        rule_lo, rule_hi = 0, 0

    raw = item.get("entry_price_range") or {}
    try:
        lo = int(raw.get("low"))
        hi = int(raw.get("high"))
    except (TypeError, ValueError):
        lo, hi = 0, 0

    current = int(candidate.get("current_price") or 0)
    if current > 0 and lo > 0 and hi > 0 and lo <= hi:
        if current * 0.85 <= lo <= current and current * 0.85 <= hi <= current:
            return _fmt_range(lo, hi), lo, hi
        logger.warning(
            "[%s] AI entry_price_range 단위 이상 (%s~%s vs current=%s) — 규칙값 사용",
            candidate.get("ticker"),
            lo,
            hi,
            current,
        )

    if rule_range:
        return rule_range, rule_lo or None, rule_hi or None
    return "", rule_lo or None, rule_hi or None


def _stock_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": row.get("ticker"),
        "symbol": row.get("name"),
        "sector": row.get("sector_name"),
        "business": row.get("business"),
        "current_price": row.get("current_price"),
        "current_price_fmt": row.get("current_price_fmt"),
        "prev_close": row.get("prev_close"),
        "day_high": row.get("day_high"),
        "day_low": row.get("day_low"),
        "trading_value_fmt": row.get("trading_value_fmt"),
        "volume_ratio": row.get("volume_ratio"),
        "foreign_net_eok": row.get("foreign_net_eok"),
        "inst_net_eok": row.get("inst_net_eok"),
        "high_52w_fmt": row.get("high_52w_fmt"),
        "pullback_from_high_pct": row.get("pullback_from_high_pct"),
        "rule_score": row.get("_pick_score"),
    }


def build_intraday_prompt(
    candidates: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    slot: str,
) -> str:
    clock, label = SCAN_SLOTS.get(slot, (slot, slot))
    allowed = ", ".join(sorted(SLACK_SEND_ALLOWED))
    forbidden = ", ".join(sorted(SLACK_SEND_FORBIDDEN))
    stocks_json = json.dumps([_stock_payload(r) for r in candidates], ensure_ascii=False, indent=2)

    return f"""장중 스캔 시간: {clock} ({label})

섹터 분위기 (strong/neutral/weak):
{json.dumps(sector_mood, ensure_ascii=False)}

아래는 규칙 기반 1차 후보 {len(candidates)}개입니다. 각 종목에 대해 슬랙 발송 여부를 판단하세요.
볼 만한 종목만 send_slack=true 로 설정하세요. 애매하거나 부정적이면 send_slack=false.

발송 허용 decision: {allowed}
발송 금지 decision: {forbidden}

후보 종목 데이터:
{stocks_json}

반드시 아래 JSON 스키마로만 응답:
{{
  "decisions": [
    {{
      "symbol": "종목명(한글)",
      "ticker": "6자리",
      "decision": "진입 검토",
      "send_slack": true,
      "entry_price_range": {{ "low": 31600, "high": 31900 }},
      "reason": "왜 지금 볼 만한지 1문장(쉬운 말투, 거래대금·억 단위 숫자 나열 금지)",
      "entry_view": "예약가 구간 눌림 확인·1주 기준 관점 1문장",
      "cancel_condition": "취소 조건 1문장(가격 이탈 또는 거래 급감, 짧게)"
    }}
  ]
}}

decisions 배열 길이는 후보 수와 같아야 합니다. 각 symbol/ticker는 후보와 일치해야 합니다.
entry_price_range의 low/high는 후보 current_price와 동일한 원(₩) 단위 정수이며, 보통 현재가의 85%~100% 구간입니다.

슬랙 문구 톤: 리포트체·로그체 금지. "활발", "증대", "데이터 불충분", 숫자 나열 문장 금지.
쉬운 말로 "왜 볼 만한지 / 어디서 눌림 볼지 / 언제 넘길지"만 짧게 씁니다."""


def _validate_decision(item: dict[str, Any], candidate: dict[str, Any]) -> str | None:
    """유효하면 None, 아니면 오류 메시지."""
    if not isinstance(item, dict):
        return "decision 항목 타입 오류"
    name = str(item.get("symbol", "")).strip()
    ticker = str(item.get("ticker", "")).zfill(6)
    cand_name = str(candidate.get("name", "")).strip()
    cand_ticker = str(candidate.get("ticker", "")).zfill(6)
    if ticker != cand_ticker and name != cand_name:
        return f"종목 불일치 (AI {ticker}/{name} vs {cand_ticker}/{cand_name})"

    decision = normalize_decision(str(item.get("decision", "")).strip())
    if not decision:
        return "decision 없음"
    if decision in SLACK_SEND_FORBIDDEN:
        return f"발송 금지 decision: {decision}"
    send_slack = item.get("send_slack")
    if send_slack is True and decision not in SLACK_SEND_ALLOWED:
        return f"send_slack=true 이지만 허용 decision 아님: {decision}"
    if send_slack is True:
        for field in ("reason", "entry_view", "cancel_condition"):
            if not str(item.get(field, "")).strip():
                return f"필수 문구 누락: {field}"
    return None


def _merge_decision(candidate: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    decision = normalize_decision(str(item.get("decision", "")).strip())
    send_slack = bool(item.get("send_slack")) and decision in SLACK_SEND_ALLOWED
    entry_range, entry_low, entry_high = _resolve_entry_range(candidate, item)

    merged = {
        **candidate,
        "status": decision,
        "ai_decision": decision,
        "ai_send_slack": send_slack,
        "ai_reason": str(item.get("reason", "")).strip(),
        "ai_entry_view": str(item.get("entry_view", "")).strip(),
        "ai_cancel_condition": str(item.get("cancel_condition", "")).strip(),
        "entry_range": entry_range,
        "entry_low": entry_low,
        "entry_high": entry_high,
    }
    if not send_slack:
        merged["ai_skip_reason"] = (
            str(item.get("skip_reason", "")).strip()
            or f"AI send_slack=false ({decision})"
        )
    return merged


def run_ai_judgments(
    candidates: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    slot: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    LLM 배치 판단.
    Returns (evaluated_rows, errors). API/파싱 실패 시 ([], errors).
    """
    if not is_ai_configured():
        return [], ["AI 미설정 (AI_PROVIDER/DEEPSEEK_API_KEY)"]
    if not candidates:
        return [], ["1차 후보 없음 — LLM 스킵"]

    prompt = build_intraday_prompt(candidates, sector_mood, slot=slot)
    parsed, err = call_llm_json(prompt, agent="kr_intraday_batch")
    if err or not parsed:
        return [], [err or "LLM 응답 없음"]

    raw_list = parsed.get("decisions")
    if not isinstance(raw_list, list):
        return [], ["LLM JSON에 decisions 배열 없음"]

    by_ticker = {str(c.get("ticker", "")).zfill(6): c for c in candidates}
    by_name = {str(c.get("name", "")).strip(): c for c in candidates}

    evaluated: list[dict[str, Any]] = []
    errors: list[str] = []

    for item in raw_list:
        if not isinstance(item, dict):
            errors.append("decisions 항목 타입 오류")
            continue
        ticker = str(item.get("ticker", "")).zfill(6)
        symbol = str(item.get("symbol", "")).strip()
        cand = by_ticker.get(ticker) or by_name.get(symbol)
        if not cand:
            errors.append(f"후보에 없는 종목: {ticker}/{symbol}")
            continue
        val_err = _validate_decision(item, cand)
        if val_err:
            errors.append(f"[{cand.get('name')}] {val_err}")
            evaluated.append(
                {
                    **cand,
                    "status": str(item.get("decision", "판단 애매")),
                    "ai_send_slack": False,
                    "ai_skip_reason": val_err,
                }
            )
            continue
        evaluated.append(_merge_decision(cand, item))

    if len(evaluated) != len(candidates):
        errors.append(
            f"decisions 개수 불일치 (후보 {len(candidates)}, 응답 {len(evaluated)})"
        )

    send_count = sum(1 for r in evaluated if r.get("ai_send_slack"))
    logger.info(
        "[KR INTRADAY AI] slot=%s candidates=%d send_slack=%d errors=%d",
        slot,
        len(candidates),
        send_count,
        len(errors),
    )
    return evaluated, errors


def build_messages_from_ai_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """ai_send_slack=True 인 행만 메시지 생성."""
    messages: list[str] = []
    send_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in rows:
        if not row.get("ai_send_slack"):
            skipped.append(
                {
                    "ticker": row.get("ticker"),
                    "name": row.get("name"),
                    "status": row.get("ai_decision") or row.get("status"),
                    "sent": False,
                    "skip_reason": row.get("ai_skip_reason") or "AI send_slack=false",
                }
            )
            continue
        msg = build_slack_message_from_ai(row)
        if not msg:
            skipped.append(
                {
                    "ticker": row.get("ticker"),
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "sent": False,
                    "skip_reason": "AI 메시지 생성 실패 또는 금지 표현",
                }
            )
            continue
        messages.append(msg)
        send_rows.append(row)

    return messages, send_rows, skipped
