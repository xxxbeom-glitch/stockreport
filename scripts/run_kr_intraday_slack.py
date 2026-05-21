#!/usr/bin/env python3
"""KR 장중 관심종목 슬랙 스캔 (05_schedule.md 시간대)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.kr_intraday_slack import SCAN_SLOTS, run_intraday_scan
from agents.kr_intraday_slack.constants import MAX_MESSAGES_PER_SCAN
from agents.kr_intraday_slack.llm_client import (
    ai_config,
    aux_models_status,
    is_ai_configured,
    is_gemini_configured,
    is_grok_configured,
)
from data.kr_watchlist import validate_watchlist_spec

SLOT_CHOICES = list(SCAN_SLOTS.keys()) + ["auto"]


def resolve_intraday_slot(slot_arg: str) -> str:
    """KST 시각 또는 auto → 0930|1050|1350|1450."""
    if slot_arg != "auto":
        return slot_arg
    kst = datetime.now(timezone(timedelta(hours=9)))
    hm = kst.strftime("%H:%M")
    if hm < "10:20":
        return "0930"
    if hm < "12:20":
        return "1050"
    if hm < "14:20":
        return "1350"
    return "1450"


def main() -> int:
    parser = argparse.ArgumentParser(description="KR 관심종목 장중 슬랙 스캔")
    parser.add_argument(
        "--slot",
        required=True,
        choices=SLOT_CHOICES,
        help="0930|1050|1350|1450|auto (auto=KST 시각 기준)",
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
    args = parser.parse_args()

    if args.dry_run and args.send:
        print("[ERROR] --dry-run 과 --send 는 동시에 사용할 수 없습니다.", file=sys.stderr)
        return 1
    if args.max_messages < 1:
        print("[ERROR] --max-messages 는 1 이상이어야 합니다.", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    spec_errors = validate_watchlist_spec()
    if spec_errors:
        print("[ERROR] watchlist spec:", spec_errors, file=sys.stderr)
        return 1

    tickers = [str(t).zfill(6) for t in (args.tickers or [])] or None
    slot = resolve_intraday_slot(args.slot)
    if args.slot == "auto":
        print(f"[KR INTRADAY] --slot auto → resolved {slot} (KST)")
    cfg = ai_config()
    aux = aux_models_status()
    print(
        f"[KR INTRADAY] AI primary={cfg['provider']}/{cfg['model']} "
        f"configured={is_ai_configured()}"
    )
    print(
        f"[KR INTRADAY] Grok optional={aux['grok']['model']} "
        f"configured={is_grok_configured()}"
    )
    print(
        f"[KR INTRADAY] Gemini optional={aux['gemini']['model']} "
        f"configured={is_gemini_configured()}"
    )

    mode = "dry_run" if args.dry_run else ("send" if args.send else "preview")
    data_src = "live" if args.live else "dummy"
    print(
        f"[KR INTRADAY] mode={mode} data={data_src} "
        f"max_messages={args.max_messages}"
    )
    if args.live and args.send:
        print("[KR INTRADAY] 운영: live 수집 + 조건 충족 시 Slack 실발송")
    elif args.live:
        print("[KR INTRADAY] live 수집, Slack 미발송 (dry-run 또는 preview)")
    elif args.send:
        print("[KR INTRADAY] 더미 시세 + Slack 실발송")

    result = run_intraday_scan(
        slot,
        live=args.live,
        tickers=tickers,
        max_messages=args.max_messages,
    )

    if args.json:
        print(
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
                    "sector_mood": result.sector_mood,
                    "messages": result.messages,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"[KR INTRADAY] {result.slot_label}")
        print(f"  scanned: {result.scanned}")
        print(f"  rule_candidates: {len(result.candidates)}")
        print(f"  ai_evaluated: {len(result.evaluated)}")
        print(f"  messages: {len(result.messages)}")
        if result.ai_errors:
            print(f"  ai_errors: {result.ai_errors}")
        if result.grok_notes:
            print(f"  grok_notes: {result.grok_notes[:5]}")
        gem_ok = sum(
            1 for r in result.send_rows if (r.get("gemini_polish") or {}).get("status") == "ok"
        )
        if result.send_rows:
            print(f"  gemini_polished: {gem_ok}/{len(result.send_rows)}")
        for msg in result.messages:
            print("---")
            print(msg)

    if args.dry_run:
        print(f"[KR INTRADAY] dry_run: 메시지 {len(result.messages)}건 생성, Slack 미발송")
        return 0

    if args.send:
        if not result.ai_enabled:
            print("[KR INTRADAY] AI 미설정 — 슬랙 미발송", file=sys.stderr)
            return 1
        if not result.messages:
            print("[KR INTRADAY] 발송 대상 0건 — 슬랙 미발송 (정상)")
            return 0
        from slack_sender import send_kr_intraday_slack

        posted = send_kr_intraday_slack(result)
        print(f"[KR INTRADAY] slack send: {posted}")
        if not posted.get("ok") and posted.get("count", 0) == 0:
            print("[KR INTRADAY] Slack API 실패", file=sys.stderr)
            return 1
    else:
        print(
            f"[KR INTRADAY] preview: 메시지 {len(result.messages)}건 "
            "(--send 없음, Slack 미발송)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
