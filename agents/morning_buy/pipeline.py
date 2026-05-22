"""📈 오늘 매수 후보 — 투표·AI 체인."""

from __future__ import annotations

from agents.kr_intraday_slack.pipeline import IntradayScanResult
from agents.kr_intraday_slack.sector_scan import merge_sector_scan_results, run_sector_scan_parallel

from .voting_flow import run_morning_voting_finalize


def run_morning_buy_alert(
    *,
    live: bool = True,
    max_messages: int = 3,
    send_empty_summary: bool = True,
) -> IntradayScanResult:
    slot = "1025"
    sector_results = run_sector_scan_parallel(
        slot=slot,
        live=live,
        include_temp_watch=True,
    )
    merged = merge_sector_scan_results(sector_results, slot=slot)
    main, send_rows, stats = run_morning_voting_finalize(
        merged.stocks,
        slot=slot,
        max_messages=max_messages,
    )

    zero = not send_rows and bool(merged.stocks)
    return IntradayScanResult(
        slot=slot,
        slot_label="10:25 오전 매수 후보",
        scanned=stats.get("scanned", len(merged.stocks)),
        candidates=merged.candidates,
        evaluated=send_rows,
        messages=[main] if main else [],
        main_message=main if (send_rows or send_empty_summary) else "",
        send_rows=send_rows,
        ai_enabled=True,
        zero_pick_notice=zero and bool(main),
    )
