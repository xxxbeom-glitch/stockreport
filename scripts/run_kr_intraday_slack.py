#!/usr/bin/env python3
"""KR 장중 관심종목 슬랙 스캔 (05_schedule.md 시간대)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.kr_intraday_slack import SCAN_SLOTS, run_intraday_scan
from agents.kr_intraday_slack.llm_client import (
    ai_config,
    aux_models_status,
    is_ai_configured,
    is_gemini_configured,
    is_grok_configured,
)
from data.kr_watchlist import validate_watchlist_spec


def main() -> int:
    parser = argparse.ArgumentParser(description="KR 관심종목 장중 슬랙 스캔")
    parser.add_argument(
        "--slot",
        required=True,
        choices=list(SCAN_SLOTS.keys()),
        help="0930|1050|1350|1450 (KST)",
    )
    parser.add_argument("--dry-run", action="store_true", help="슬랙 발송 없이 결과만 출력")
    parser.add_argument("--send", action="store_true", help="조건 충족 시 Slack 발송")
    parser.add_argument("--json", action="store_true", help="JSON 요약 출력")
    parser.add_argument(
        "--live",
        action="store_true",
        help="KIS/pykrx 라이브 수집 (실패 시 더미 대체 없음, 로그 기록)",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        dest="tickers",
        metavar="CODE",
        help="테스트용: 특정 티커만 (예: --ticker 089030). 여러 번 지정 가능",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    spec_errors = validate_watchlist_spec()
    if spec_errors:
        print("[ERROR] watchlist spec:", spec_errors, file=sys.stderr)
        return 1

    tickers = [str(t).zfill(6) for t in (args.tickers or [])] or None
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

    result = run_intraday_scan(args.slot, live=args.live, tickers=tickers)

    if args.json:
        print(
            json.dumps(
                {
                    "slot": result.slot,
                    "slot_label": result.slot_label,
                    "live": args.live,
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
        print("[KR INTRADAY] --dry-run: 슬랙 발송 생략")
    elif args.send:
        if not result.messages:
            print("[KR INTRADAY] AI 승인 메시지 없음 — 슬랙 미발송")
        elif not result.ai_enabled:
            print("[KR INTRADAY] AI 미설정 — 슬랙 미발송")
        else:
            from slack_sender import send_kr_intraday_slack

            posted = send_kr_intraday_slack(result)
            print(f"[KR INTRADAY] slack send: {posted}")
    elif not result.messages:
        print("[KR INTRADAY] 슬랙 미발송 (AI 판단 없음 또는 send_slack=false)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
