"""장중 관심종목 스캔 파이프라인 (03~07 통합 + 멀티 모델 LLM)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .ai_judge import run_ai_judgments
from .constants import SCAN_SLOTS
from .gemini_polish import polish_slack_message
from .grok_social import enrich_rows_with_grok
from .llm_client import aux_models_status, is_ai_configured
from .market_data import collect_watchlist_market_data
from .sector_mood import judge_sector_mood
from .send_filter import filter_for_slack_send
from .send_log import append_log_record
from .slack_message import build_slack_message_from_ai
from .watchlist_pick import pick_watchlist_candidates

logger = logging.getLogger("kr_intraday.pipeline")


@dataclass
class IntradayScanResult:
    slot: str
    slot_label: str
    sector_mood: dict[str, str] = field(default_factory=dict)
    scanned: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    evaluated: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    send_rows: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    ai_enabled: bool = False
    ai_errors: list[str] = field(default_factory=list)
    aux_models: dict[str, Any] = field(default_factory=dict)
    grok_notes: list[str] = field(default_factory=list)

    @property
    def should_send_slack(self) -> bool:
        return bool(self.messages)


def _log_row(row: dict[str, Any], *, slot: str) -> None:
    """DeepSeek + Grok + Gemini 메타를 발송 로그에 함께 기록."""
    record: dict[str, Any] = {
        "slot": slot,
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "status": row.get("ai_decision") or row.get("status"),
        "ai_send_slack": row.get("ai_send_slack"),
        "ai_decision": row.get("ai_decision"),
        "ai_reason": row.get("ai_reason"),
        "grok_status": row.get("grok_status"),
        "grok_skip_reason": row.get("grok_skip_reason"),
        "grok_context": row.get("grok_context"),
        "gemini_polish": row.get("gemini_polish"),
        "slack_message_draft": row.get("slack_message_draft"),
    }
    if row.get("sent") is not None:
        record["sent"] = row.get("sent")
    if row.get("skip_reason"):
        record["skip_reason"] = row.get("skip_reason")
    append_log_record(record)


def run_intraday_scan(
    slot: str,
    *,
    live: bool = False,
    tickers: list[str] | None = None,
    max_messages: int | None = None,
) -> IntradayScanResult:
    """
    시간대별 관심종목 스캔.
    슬랙 메시지는 DeepSeek ai_send_slack=true + 허용 decision 일 때만 생성.
    Grok/Gemini는 optional — 키 없거나 실패 시 skip, 더미 대체 없음.
    """
    if slot not in SCAN_SLOTS:
        raise ValueError(f"Unknown slot: {slot}. Use one of {list(SCAN_SLOTS)}")

    clock, label = SCAN_SLOTS[slot]
    ai_enabled = is_ai_configured()
    aux = aux_models_status()
    logger.info(
        "[KR INTRADAY] models primary=%s grok=%s gemini=%s",
        aux["primary"]["configured"],
        aux["grok"]["configured"],
        aux["gemini"]["configured"],
    )

    stocks = collect_watchlist_market_data(slot, live=live, tickers=tickers)
    mood = judge_sector_mood(stocks, slot)
    picks = pick_watchlist_candidates(stocks, mood, slot=slot)

    messages: list[str] = []
    send_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    evaluated: list[dict[str, Any]] = []
    ai_errors: list[str] = []
    grok_notes: list[str] = []

    if not ai_enabled:
        ai_errors.append("AI 미설정 — 슬랙 메시지 생성 안 함 (DEEPSEEK_API_KEY, AI_PROVIDER 확인)")
        logger.error("[KR INTRADAY] %s", ai_errors[0])
    elif not picks:
        ai_errors.append("규칙 1차 후보 0건 — LLM 미호출")
        logger.info("[KR INTRADAY] %s", ai_errors[0])
    else:
        evaluated, ai_errors = run_ai_judgments(picks, mood, slot=slot)
        if ai_errors and not evaluated:
            logger.error("[KR INTRADAY] LLM 판단 실패: %s", "; ".join(ai_errors))
        elif ai_errors:
            for e in ai_errors:
                logger.warning("[KR INTRADAY AI] %s", e)

        if evaluated:
            evaluated, grok_notes = enrich_rows_with_grok(evaluated, mood, slot=slot)

            for row in evaluated:
                if not row.get("ai_send_slack"):
                    skip_entry = {
                        "ticker": row.get("ticker"),
                        "name": row.get("name"),
                        "status": row.get("ai_decision") or row.get("status"),
                        "sent": False,
                        "skip_reason": row.get("ai_skip_reason") or "AI send_slack=false",
                    }
                    skipped.append(skip_entry)
                    _log_row({**row, **skip_entry}, slot=slot)

            ai_approved = [r for r in evaluated if r.get("ai_send_slack")]
            to_send, filter_skip = filter_for_slack_send(
                ai_approved,
                slot=slot,
                require_ai=True,
                max_messages=max_messages,
            )
            skipped.extend(filter_skip)
            for fs in filter_skip:
                _log_row(fs, slot=slot)

            for row in to_send:
                draft = build_slack_message_from_ai(row)
                if not draft:
                    skip_entry = {
                        "ticker": row.get("ticker"),
                        "name": row.get("name"),
                        "sent": False,
                        "skip_reason": "AI 메시지 본문 생성 실패",
                    }
                    skipped.append(skip_entry)
                    _log_row({**row, **skip_entry}, slot=slot)
                    continue

                final, gem_meta = polish_slack_message(draft, row)
                out_row = {
                    **row,
                    "slack_message_draft": draft,
                    "slack_message": final,
                    "gemini_polish": gem_meta,
                }
                messages.append(final)
                send_rows.append(out_row)
                _log_row(out_row, slot=slot)

    result = IntradayScanResult(
        slot=slot,
        slot_label=f"{clock} {label}",
        sector_mood=mood,
        scanned=len(stocks),
        candidates=picks,
        evaluated=evaluated,
        messages=messages,
        send_rows=send_rows,
        skipped=skipped,
        ai_enabled=ai_enabled,
        ai_errors=ai_errors,
        aux_models=aux,
        grok_notes=grok_notes,
    )

    if not messages:
        reason = (
            "; ".join(ai_errors)
            if ai_errors
            else "AI 승인 종목 없음 — 슬랙 미발송"
        )
        append_log_record(
            {
                "slot": slot,
                "ticker": "",
                "name": "",
                "status": "",
                "sent": False,
                "skip_reason": reason,
                "aux_models": aux,
            }
        )
        logger.info("[KR INTRADAY] 슬랙 메시지 없음: %s", reason)

    return result
