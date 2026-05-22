"""장중 관심종목 스캔 — 단타 판단 보조 Slack 파이프라인 (섹터 병렬 + 배치 LLM)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .ai_judge import run_ai_judgments
from .entry_price import enrich_intraday_entry
from .constants import SCAN_SLOTS
from .gemini_polish import polish_slack_message
from .grok_social import enrich_rows_with_grok
from .llm_client import aux_models_status, is_ai_configured
from .message_tone import (
    compose_daily_pick_zero_message,
    compose_new_candidate_stock_block,
    select_pass_today_rows,
)
from .sector_scan import merge_sector_scan_results, run_sector_scan_parallel
from .send_filter import filter_for_slack_send
from .send_log import append_log_record
from .slack_message import build_intraday_slack_thread_bundle

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
    main_message: str = ""
    thread_messages: list[dict[str, Any]] = field(default_factory=list)
    send_rows: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    ai_enabled: bool = False
    ai_errors: list[str] = field(default_factory=list)
    aux_models: dict[str, Any] = field(default_factory=dict)
    grok_notes: list[str] = field(default_factory=list)
    sector_scan_notes: list[str] = field(default_factory=list)
    zero_pick_notice: bool = False

    @property
    def should_send_slack(self) -> bool:
        return bool(self.main_message)


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
    send_empty_summary: bool = False,
) -> IntradayScanResult:
    """
    시간대별 관심종목 스캔.
    1) 5개 섹터 병렬: 시세 수집 + 1차 후보
    2) merge → DeepSeek 배치 1회 (최대 7종목)
    3) SendFilter → 종목별 Gemini polish → 메인 요약 + 섹터별 쓰레드
    """
    if slot not in SCAN_SLOTS:
        raise ValueError(f"Unknown slot: {slot}. Use one of {list(SCAN_SLOTS)}")

    clock, label = SCAN_SLOTS[slot]
    ai_enabled = is_ai_configured()
    aux = aux_models_status()
    logger.info(
        "[KR INTRADAY] models primary=%s grok=%s gemini=%s parallel_sectors=5",
        aux["primary"]["configured"],
        aux["grok"]["configured"],
        aux["gemini"]["configured"],
    )

    sector_results = run_sector_scan_parallel(
        slot=slot,
        live=live,
        tickers=tickers,
    )
    try:
        from utils.safe_stdio import ensure_stdio

        ensure_stdio()
    except ImportError:
        pass
    merged = merge_sector_scan_results(sector_results, slot=slot)
    stocks = merged.stocks
    mood = merged.sector_mood
    picks = merged.candidates
    sector_notes = merged.notes

    messages: list[str] = []
    main_message = ""
    thread_messages: list[dict[str, Any]] = []
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
        picks = [enrich_intraday_entry(p, slot=slot) for p in picks]
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

            polished_rows: list[dict[str, Any]] = []
            for row in to_send:
                draft = compose_new_candidate_stock_block(row) or ""
                if not draft:
                    skipped.append(
                        {
                            "ticker": row.get("ticker"),
                            "name": row.get("name"),
                            "sent": False,
                            "skip_reason": "종목 블록 생성 실패",
                        }
                    )
                    continue
                final_block, gem_meta = polish_slack_message(draft, row)
                polished_rows.append(
                    {
                        **row,
                        "slack_stock_block": final_block,
                        "slack_message_draft": draft,
                        "gemini_polish": gem_meta,
                    }
                )

            pass_rows: list[dict[str, Any]] = []
            for row in select_pass_today_rows(evaluated, polished_rows):
                block = compose_new_candidate_stock_block(row, pass_today=True)
                if block:
                    pass_rows.append({**row, "slack_stock_block": block})

            bundle = None
            if polished_rows or pass_rows:
                bundle = build_intraday_slack_thread_bundle(
                    polished_rows,
                    slot=slot,
                    allow_empty=False,
                    pass_rows=pass_rows,
                    evaluated=evaluated,
                )
            if bundle is not None:
                if not bundle.get("main"):
                    ai_errors.append("슬랙 메인·쓰레드 메시지 생성 실패")
                    logger.error("[KR INTRADAY] %s", ai_errors[-1])
                else:
                    main_message = bundle["main"]
                    thread_messages = list(bundle["threads"])
                    messages.append(main_message)
                    for th in thread_messages:
                        messages.append(th["text"])
                    for row in polished_rows:
                        out_row = {
                            **row,
                            "slack_message": main_message,
                        }
                        send_rows.append(out_row)
                        _log_row(out_row, slot=slot)

    zero_pick_notice = False
    if (
        not main_message
        and send_empty_summary
        and len(stocks) > 0
        and ai_enabled
    ):
        qualified = len(send_rows)
        main_message = compose_daily_pick_zero_message(
            slot=slot,
            scanned=len(stocks),
            qualified_count=qualified,
        )
        if main_message:
            messages = [main_message]
            zero_pick_notice = True
            logger.info(
                "[DAILY_PICK] 후보 0건 안내 메시지 준비 (scanned=%s qualified=%s)",
                len(stocks),
                qualified,
            )

    result = IntradayScanResult(
        slot=slot,
        slot_label=f"{clock} {label}",
        sector_mood=mood,
        scanned=len(stocks),
        candidates=picks,
        evaluated=evaluated,
        messages=messages,
        main_message=main_message,
        thread_messages=thread_messages,
        send_rows=send_rows,
        skipped=skipped,
        ai_enabled=ai_enabled,
        ai_errors=ai_errors,
        aux_models=aux,
        grok_notes=grok_notes,
        sector_scan_notes=sector_notes,
        zero_pick_notice=zero_pick_notice,
    )

    if not main_message:
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
                "sector_scan_notes": sector_notes,
            }
        )
        logger.info("[KR INTRADAY] 슬랙 메시지 없음: %s", reason)

    return result
