#!/usr/bin/env python3
"""KR 장중 관심종목 슬랙 스캔 (05_schedule.md 시간대)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.safe_stdio import (  # noqa: E402
    ensure_stdio,
    safe_print,
    safe_print_exception,
    setup_logging,
)

from agents.kr_intraday_slack import SCAN_SLOTS, run_intraday_scan  # noqa: E402
from agents.kr_intraday_slack.constants import MAX_MESSAGES_PER_SCAN  # noqa: E402
from agents.kr_intraday_slack.llm_client import (  # noqa: E402
    ai_config,
    aux_models_status,
    is_ai_configured,
    is_gemini_configured,
    is_grok_configured,
)
from data.kr_watchlist import validate_watchlist_spec  # noqa: E402

SLOT_CHOICES = list(SCAN_SLOTS.keys()) + ["auto"]


def resolve_intraday_slot(slot_arg: str) -> str:
    """KST 시각 또는 auto → 1030|1350."""
    if slot_arg != "auto":
        return slot_arg
    kst = datetime.now(timezone(timedelta(hours=9)))
    hm = kst.strftime("%H:%M")
    if hm < "12:00":
        return "1030"
    return "1350"


def main() -> int:
    ensure_stdio()
    setup_logging()

    parser = argparse.ArgumentParser(description="KR 관심종목 장중 슬랙 스캔")
    parser.add_argument(
        "--slot",
        required=True,
        choices=SLOT_CHOICES,
        help="1030|1350|auto (auto=KST 시각 기준: ~12시 이전 1030, 이후 1350)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="슬랙 발송 없이 메시지 초안만 생성·출력",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="조건 충족 시 Slack 실발송 (운영)",
    )
    parser.add_argument("--json", action="store_true", help="JSON 요약 출력")
    parser.add_argument(
        "--live",
        action="store_true",
        help="KIS/pykrx 라이브 수집 (미지정 시 더미/로컬 시세)",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=MAX_MESSAGES_PER_SCAN,
        metavar="N",
        help=f"슬랙 최대 발송 건수 (기본 {MAX_MESSAGES_PER_SCAN}, SendFilter)",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        dest="tickers",
        metavar="CODE",
        help="특정 티커만 스캔 (예: --ticker 222800). 여러 번 지정 가능",
    )
    parser.add_argument(
        "--send-empty-summary",
        action="store_true",
        help="진입 후보 0건이어도 메인+섹터 쓰레드 발송 (수동 확인용)",
    )
    args = parser.parse_args()

    if args.dry_run and args.send:
        safe_print(
            "[ERROR] --dry-run 과 --send 는 동시에 사용할 수 없습니다.",
            file=sys.__stderr__,
        )
        return 1
    if args.max_messages < 1:
        safe_print("[ERROR] --max-messages 는 1 이상이어야 합니다.", file=sys.__stderr__)
        return 1

    try:
        return _run(args)
    except Exception as exc:
        safe_print_exception(exc, prefix="[KR INTRADAY] FATAL")
        return 1
    finally:
        ensure_stdio()


def _run(args: argparse.Namespace) -> int:
    spec_errors = validate_watchlist_spec()
    if spec_errors:
        safe_print("[ERROR] watchlist spec:", spec_errors, file=sys.__stderr__)
        return 1

    tickers = [str(t).zfill(6) for t in (args.tickers or [])] or None
    slot = resolve_intraday_slot(args.slot)
    if args.slot == "auto":
        safe_print(f"[KR INTRADAY] --slot auto → resolved {slot} (KST)")
    cfg = ai_config()
    aux = aux_models_status()
    safe_print(
        f"[KR INTRADAY] AI primary={cfg['provider']}/{cfg['model']} "
        f"configured={is_ai_configured()}"
    )
    safe_print(
        f"[KR INTRADAY] Grok optional={aux['grok']['model']} "
        f"configured={is_grok_configured()}"
    )
    safe_print(
        f"[KR INTRADAY] Gemini optional={aux['gemini']['model']} "
        f"configured={is_gemini_configured()}"
    )

    mode = "dry_run" if args.dry_run else ("send" if args.send else "preview")
    data_src = "live" if args.live else "dummy"
    safe_print(
        f"[KR INTRADAY] mode={mode} data={data_src} "
        f"max_messages={args.max_messages}"
    )
    if args.live and args.send:
        safe_print("[KR INTRADAY] 운영: live 수집 + 조건 충족 시 Slack 실발송")
    elif args.live:
        safe_print("[KR INTRADAY] live 수집, Slack 미발송 (dry-run 또는 preview)")
    elif args.send:
        safe_print("[KR INTRADAY] 더미 시세 + Slack 실발송")

    ensure_stdio()
    result = run_intraday_scan(
        slot,
        live=args.live,
        tickers=tickers,
        max_messages=args.max_messages,
        send_empty_summary=args.send_empty_summary,
    )
    ensure_stdio()

    if args.json:
        safe_print(
            json.dumps(
                {
                    "slot": result.slot,
                    "slot_label": result.slot_label,
                    "mode": mode,
                    "live": args.live,
                    "max_messages": args.max_messages,
                    "ai_enabled": result.ai_enabled,
                    "ai_errors": result.ai_errors,
                    "ai_model": cfg["model"],
                    "aux_models": result.aux_models,
                    "grok_notes": result.grok_notes,
                    "tickers": tickers,
                    "scanned": result.scanned,
                    "rule_candidates": len(result.candidates),
                    "ai_evaluated": len(result.evaluated),
                    "message_count": len(result.messages),
                    "main_message": result.main_message,
                    "thread_count": len(result.thread_messages),
                    "sector_mood": result.sector_mood,
                    "messages": result.messages,
                    "thread_messages": result.thread_messages,
                    "sector_scan_notes": result.sector_scan_notes,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        safe_print(f"[KR INTRADAY] {result.slot_label}")
        safe_print(f"  scanned: {result.scanned}")
        safe_print(f"  rule_candidates: {len(result.candidates)}")
        safe_print(f"  ai_evaluated: {len(result.evaluated)}")
        safe_print(f"  messages: {len(result.messages)} (main + {len(result.thread_messages)} threads)")
        if result.ai_errors:
            safe_print(f"  ai_errors: {result.ai_errors}")
        if result.grok_notes:
            safe_print(f"  grok_notes: {result.grok_notes[:5]}")
        gem_ok = sum(
            1
            for r in result.send_rows
            if (r.get("gemini_polish") or {}).get("status") == "ok"
        )
        if result.send_rows:
            safe_print(f"  gemini_polished: {gem_ok}/{len(result.send_rows)}")
        if result.main_message:
            safe_print("--- MAIN ---")
            safe_print(result.main_message)
        for th in result.thread_messages:
            safe_print(f"--- THREAD: {th.get('sector', '')} ---")
            safe_print(th.get("text", ""))

    if args.dry_run:
        safe_print(
            f"[KR INTRADAY] dry_run: main + {len(result.thread_messages)} threads, Slack 미발송"
        )
        return 0

    if args.send:
        if not result.ai_enabled:
            safe_print("[KR INTRADAY] AI 미설정 — 슬랙 미발송", file=sys.__stderr__)
            return 1
        if not result.main_message:
            safe_print("[KR INTRADAY] 발송 대상 0건 — 슬랙 미발송 (정상)")
            safe_print(
                "[KR INTRADAY] 0건이어도 메인을내려면 --send-empty-summary 와 함께 실행"
            )
            return 0
        from slack_sender import send_kr_intraday_slack

        ensure_stdio()
        posted = send_kr_intraday_slack(result)
        ensure_stdio()
        safe_print(f"[KR INTRADAY] slack send: {posted}")
        if not posted.get("ok") and posted.get("count", 0) == 0:
            safe_print("[KR INTRADAY] Slack API 실패", file=sys.__stderr__)
            return 1
    else:
        safe_print(
            f"[KR INTRADAY] preview: main + {len(result.thread_messages)} threads "
            "(--send 없음, Slack 미발송)"
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        safe_print_exception(exc, prefix="[KR INTRADAY] UNHANDLED")
        raise SystemExit(1) from exc
