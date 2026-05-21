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
from .entry_price import (
    build_entry_range_fallback,
    format_entry_range,
    has_valid_entry_range,
    normalize_ai_entry_range,
)
from .llm_client import call_llm_json, is_ai_configured
from .slack_message import build_slack_message_from_ai

logger = logging.getLogger("kr_intraday.ai_judge")

RULE_CANDIDATE_MIN = 3
RULE_CANDIDATE_MAX = 7


def _parse_ai_range(item: dict[str, Any]) -> tuple[int, int]:
    raw = item.get("entry_price_range") or {}
    try:
        return int(raw.get("low")), int(raw.get("high"))
    except (TypeError, ValueError):
        return 0, 0


def _log_entry_resolution(
    candidate: dict[str, Any],
    *,
    kind: str,
    detail: str,
    low: int = 0,
    high: int = 0,
) -> None:
    ticker = candidate.get("ticker")
    name = candidate.get("name")
    if kind == "ai_ok":
        logger.info(
            "[%s %s] 진입 구간: AI range 사용 (%s~%s)",
            ticker,
            name,
            f"{low:,}",
            f"{high:,}",
        )
    elif kind == "ai_adjusted":
        logger.info(
            "[%s %s] 진입 구간: AI range 보정 (%s) (%s~%s)",
            ticker,
            name,
            detail,
            f"{low:,}",
            f"{high:,}",
        )
    elif kind == "rule_fallback":
        logger.info(
            "[%s %s] 진입 구간: 규칙 fallback (%s) %s",
            ticker,
            name,
            detail,
            format_entry_range(low, high) if low and high else detail,
        )
    elif kind == "rule_candidate":
        logger.info(
            "[%s %s] 진입 구간: 후보 규칙값 사용 %s",
            ticker,
            name,
            format_entry_range(low, high),
        )
    elif kind == "unavailable":
        logger.warning(
            "[%s %s] 진입 구간: 계산 불가 — 발송 제외 (%s)",
            ticker,
            name,
            detail,
        )


def _resolve_entry_range(
    candidate: dict[str, Any], item: dict[str, Any]
) -> tuple[str, int | None, int | None, str]:
    """
    진입 후보 구간 확정.

    Returns (entry_range, entry_low, entry_high, source)
    source: ai | ai_adjusted | rule_candidate | rule_anchor | rule_default | unavailable
    """
    current = int(candidate.get("current_price") or 0)
    ai_lo, ai_hi = _parse_ai_range(item)

    if current > 0 and ai_lo > 0 and ai_hi > 0:
        norm_lo, norm_hi, status = normalize_ai_entry_range(ai_lo, ai_hi, current)
        if status not in ("invalid", "out_of_band") and norm_lo > 0 and norm_hi > 0:
            text = format_entry_range(norm_lo, norm_hi)
            if status == "ok":
                _log_entry_resolution(candidate, kind="ai_ok", detail="", low=norm_lo, high=norm_hi)
                return text, norm_lo, norm_hi, "ai"
            _log_entry_resolution(
                candidate,
                kind="ai_adjusted",
                detail=status,
                low=norm_lo,
                high=norm_hi,
            )
            return text, norm_lo, norm_hi, "ai_adjusted"
        _log_entry_resolution(
            candidate,
            kind="ai_adjusted",
            detail=f"AI 밴드 밖({ai_lo}~{ai_hi} vs current={current}) → fallback",
            low=0,
            high=0,
        )
    elif ai_lo > 0 or ai_hi > 0:
        logger.info(
            "[%s] AI entry_price_range 파싱/밴드 불가 (%s~%s) — fallback",
            candidate.get("ticker"),
            ai_lo,
            ai_hi,
        )

    try:
        rule_lo = int(candidate.get("entry_low") or 0)
        rule_hi = int(candidate.get("entry_high") or 0)
    except (TypeError, ValueError):
        rule_lo, rule_hi = 0, 0

    if current > 0 and rule_lo > 0 and rule_hi > 0:
        norm_lo, norm_hi, status = normalize_ai_entry_range(rule_lo, rule_hi, current)
        if status not in ("invalid", "out_of_band") and norm_lo > 0 and norm_hi > 0:
            text = format_entry_range(norm_lo, norm_hi)
            _log_entry_resolution(
                candidate, kind="rule_candidate", detail="", low=norm_lo, high=norm_hi
            )
            return text, norm_lo, norm_hi, "rule_candidate"

    text, fb_lo, fb_hi, source = build_entry_range_fallback(candidate)
    if has_valid_entry_range(text, entry_low=fb_lo, entry_high=fb_hi):
        _log_entry_resolution(
            candidate, kind="rule_fallback", detail=source, low=fb_lo, high=fb_hi
        )
        return text, fb_lo, fb_hi, source

    _log_entry_resolution(candidate, kind="unavailable", detail="current_price 없음 또는 0")
    return "", None, None, "unavailable"


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
      "entry_view": "진입 후보 구간(매수 타이밍 노릴 가격대) 눌림·1주 기준 1문장",
      "cancel_condition": "경고 1문장(매수가 아님·진입 구간 무효·가격 이탈 또는 거래 급감 시 오늘은 넘기기, '취소 조건' 단어 금지)"
    }}
  ]
}}

decisions 배열 길이는 후보 수와 같아야 합니다. 각 symbol/ticker는 후보와 일치해야 합니다.
entry_price_range의 low/high는 후보 current_price와 동일한 원(₩) 단위 정수입니다.
high는 current_price를 넘지 않게 하고, 보통 현재가의 70%~100% 구간(눌림 목표)으로 잡습니다.

슬랙 문구 톤: 리포트체·로그체 금지. "활발", "증대", "데이터 불충분", 숫자 나열 문장 금지.
쉬운 말로 "왜 볼 만한지 / 진입 후보 구간(1주 기준 노릴 가격대) / 경고(매수가 아님·이탈·거래 급감 시 오늘은 넘기기)"만 씁니다.
reason·entry_view·cancel_condition은 완성 문장만, 줄임표(...) 금지.
슬랙 본문에는 '취소 조건' 대신 '경고' 표현을 쓰도록 cancel_condition 문장을 작성합니다."""


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
    entry_range, entry_low, entry_high, source = _resolve_entry_range(candidate, item)

    if send_slack and not has_valid_entry_range(
        entry_range, entry_low=entry_low, entry_high=entry_high
    ):
        send_slack = False
        skip = "진입 후보 구간 계산 불가"
    else:
        skip = ""

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
        "entry_range_source": source,
    }
    if not send_slack:
        merged["ai_skip_reason"] = (
            skip
            or str(item.get("skip_reason", "")).strip()
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
