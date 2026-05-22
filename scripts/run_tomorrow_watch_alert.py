#!/usr/bin/env python3
"""🌙 내일 볼 종목 알림."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.safe_stdio import ensure_stdio, safe_print, setup_logging  # noqa: E402
from utils.workflow_run_log import WorkflowRunLog  # noqa: E402

from agents.ai.model_config import log_model_banner  # noqa: E402
from agents.tomorrow_watch import run_tomorrow_watch_alert  # noqa: E402
from utils.safe_mode import can_send_candidate_slack, print_candidate_scan_status  # noqa: E402


def main() -> int:
    ensure_stdio()
    setup_logging()
    parser = argparse.ArgumentParser(description="내일 볼 종목 알림")
    parser.add_argument("--live-data", action="store_true", help="실제 데이터로 확인")
    parser.add_argument("--send-slack", action="store_true", help="Slack으로 보내기")
    parser.add_argument("--scan-count", type=int, default=60, help="스캔 종목 수")
    parser.add_argument("--max-pick", type=int, default=5, help="최대 선정 종목 수")
    parser.add_argument("--scheduled", action="store_true", help="Actions schedule 실행")
    args = parser.parse_args()

    scheduled_kst = "15:55" if args.scheduled else "수동"
    log = WorkflowRunLog("내일 볼 종목 알림", scheduled_kst, tag="TOMORROW_WATCH")
    log.banner_start(fn=safe_print)
    log_model_banner(emit=safe_print)
    print_candidate_scan_status(emit=safe_print)

    t0 = time.monotonic()
    result = run_tomorrow_watch_alert(
        scan_limit=max(1, args.scan_count),
        max_pick=max(1, args.max_pick),
        live=args.live_data,
        on_progress=safe_print,
    )
    log.counts["전체 스캔 종목 수"] = result.scanned
    log.counts["정량 1차 필터 통과 수"] = result.quant_passed
    log.counts["에이전트 투표"] = result.voted
    log.counts["trend_score 적용"] = result.trend_applied
    log.counts["Gemini"] = f"{result.gemini_selected} ({result.gemini_status})"
    log.counts["DART 새 중요공시"] = result.dart_new_count
    log.counts["Grok"] = (
        f"{result.grok_checked} web={result.grok_web_search_used} x={result.grok_x_search_used}"
    )
    log.counts["DeepSeek"] = f"{result.deepseek_final} ({result.deepseek_status})"
    log.counts["0건 안내 발송"] = "예정" if args.send_slack else "dry-run"

    safe_print("--- SLACK PREVIEW ---")
    safe_print(result.slack_text[:6000])

    if args.send_slack:
        if not can_send_candidate_slack(explicit_cli=True):
            safe_print("[TOMORROW_WATCH] Slack 발송 차단")
            log.finish(ok=False, fn=safe_print)
            return 1
        from slack_sender import post_buy_candidate_message

        posted = post_buy_candidate_message(result.slack_text, retries=1)
        log.mark_slack_sent()
        ok = bool(posted.get("ok"))
        log.counts["Slack 발송"] = "성공" if ok else "실패"
        if result.final_picks:
            safe_print(f"[TOMORROW_WATCH] 후보 {len(result.final_picks)}건 Slack 발송 완료")
        else:
            safe_print("[TOMORROW_WATCH] 후보 0건 안내 메시지 Slack 발송 완료")
        if result.store_path:
            safe_print(f"[TOMORROW_WATCH] 저장: {result.store_path}")
        log.finish(ok=ok, fn=safe_print)
        return 0 if ok else 1

    safe_print(f"[TOMORROW_WATCH] dry-run 완료 ({time.monotonic() - t0:.1f}s)")
    log.finish(ok=True, fn=safe_print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
