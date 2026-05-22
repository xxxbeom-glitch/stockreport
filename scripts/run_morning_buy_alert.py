#!/usr/bin/env python3
"""📈 오늘 매수 후보 알림."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.safe_stdio import ensure_stdio, safe_print, setup_logging  # noqa: E402
from utils.workflow_run_log import WorkflowRunLog  # noqa: E402

from agents.ai.model_config import log_model_banner  # noqa: E402
from agents.morning_buy import run_morning_buy_alert  # noqa: E402
from data.candidates.temporary_watch import list_active_temp_candidates  # noqa: E402
from utils.safe_mode import can_send_daily_pick_slack, print_daily_pick_status  # noqa: E402


def main() -> int:
    ensure_stdio()
    setup_logging()
    parser = argparse.ArgumentParser(description="오늘 매수 후보 알림")
    parser.add_argument("--live-data", action="store_true", help="실제 데이터로 확인")
    parser.add_argument("--send-slack", action="store_true", help="Slack으로 보내기")
    parser.add_argument("--max-pick", type=int, default=3, help="최대 발송 개수")
    parser.add_argument("--scheduled", action="store_true", help="Actions schedule 실행")
    args = parser.parse_args()

    scheduled_kst = "10:25" if args.scheduled else "수동"
    log = WorkflowRunLog("오늘 매수 후보 알림", scheduled_kst, tag="MORNING_BUY")
    log.banner_start(fn=safe_print)
    log_model_banner(emit=safe_print)
    print_daily_pick_status(emit=safe_print)
    temps = list_active_temp_candidates()
    safe_print(f"[MORNING_BUY] 임시 관찰 후보 {len(temps)}건 포함")

    if args.send_slack and not can_send_daily_pick_slack(
        explicit_cli=True, scheduled=args.scheduled
    ):
        safe_print("[MORNING_BUY] Slack 발송 차단 — dry-run")
        args.send_slack = False

    result = run_morning_buy_alert(
        live=args.live_data,
        max_messages=max(1, args.max_pick),
        send_empty_summary=args.send_slack or True,
    )

    log.counts["전체 스캔 종목 수"] = result.scanned
    log.counts["정량 1차 필터 통과 수"] = len(result.candidates)
    log.counts["DeepSeek 최종 판단 수"] = len(result.evaluated)
    log.counts["Slack 발송 대상"] = len(result.send_rows)

    if result.main_message:
        safe_print("--- MAIN ---")
        safe_print(result.main_message)

    if args.send_slack:
        if not result.main_message:
            safe_print("[MORNING_BUY] 메시지 없음", file=sys.stderr)
            log.finish(ok=False, fn=safe_print)
            return 1
        from slack_sender import send_kr_intraday_slack

        posted = send_kr_intraday_slack(result)
        log.mark_slack_sent()
        ok = bool(posted.get("ok"))
        log.counts["Slack 발송"] = "성공" if ok else "실패"
        if result.zero_pick_notice:
            safe_print("[MORNING_BUY] 후보 0건 안내 메시지 Slack 발송 완료")
        elif result.send_rows:
            safe_print(f"[MORNING_BUY] 매수 후보 {len(result.send_rows)}건 Slack 발송 완료")
        log.finish(ok=ok, fn=safe_print)
        return 0 if ok else 1

    safe_print("[MORNING_BUY] dry-run 완료 (Slack 미발송)")
    log.finish(ok=True, fn=safe_print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
