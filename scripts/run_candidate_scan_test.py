#!/usr/bin/env python3
"""신규 후보 스캔 테스트 — 제안 JSON·daily_scan 저장만 (watchlist 자동 수정 없음)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.safe_stdio import ensure_stdio, safe_print, setup_logging  # noqa: E402

from agents.weekly_watchlist_update.candidate_report import (  # noqa: E402
    build_candidate_slack_text,
    write_candidate_outputs,
)
from agents.weekly_watchlist_update.candidate_scanner import (  # noqa: E402
    format_candidate_scan_log_lines,
    run_candidate_scan,
)
from data.kr_market import get_trading_date  # noqa: E402
from utils.safe_mode import (  # noqa: E402
    can_send_candidate_slack,
    print_candidate_scan_status,
    print_watchlist_review_status,
)


def _as_of_iso() -> str:
    raw = get_trading_date()
    if len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def main() -> int:
    ensure_stdio()
    setup_logging()

    parser = argparse.ArgumentParser(
        description="신규 후보 스캔 테스트 (제안만, watchlist 미수정)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scan-count",
        type=int,
        default=30,
        metavar="N",
        help="스캔 종목 수 (섹터 우선순위 상위 N)",
    )
    parser.add_argument(
        "--trend-days",
        type=int,
        default=5,
        metavar="N",
        help="최근 며칠 흐름 (daily_scan 누적)",
    )
    parser.add_argument(
        "--live-data",
        action="store_true",
        help="실제 데이터로 확인 (pykrx OHLCV 조회)",
    )
    parser.add_argument(
        "--send-slack",
        action="store_true",
        help="Slack으로 보내기 (기본: 제안 JSON만)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="기준일 YYYY-MM-DD (기본: 최근 거래일)",
    )
    args = parser.parse_args()

    print_candidate_scan_status(emit=safe_print)
    print_watchlist_review_status(emit=safe_print)

    as_of = args.as_of or _as_of_iso()
    safe_print(f"[CANDIDATES] 신규 후보 스캔 테스트 (as_of={as_of})")

    if not args.live_data:
        safe_print("[CANDIDATES] live-data 미사용 — 스캔은 실행되나 OHLCV는 조회하지 않습니다.")
        safe_print("[CANDIDATES] 실제 스캔을 하려면 --live-data 를 추가하세요.")
        return 0

    try:
        cand = run_candidate_scan(
            as_of_date=as_of,
            scan_limit=max(1, args.scan_count),
            candidate_days=max(1, args.trend_days),
            on_progress=safe_print,
        )
    except Exception as exc:
        safe_print(f"[CANDIDATES] 실패: {exc}")
        return 1

    cand_path = write_candidate_outputs(cand)
    for line in format_candidate_scan_log_lines(cand):
        safe_print(line)
    if cand_path:
        safe_print(f"[CANDIDATES] saved: {cand_path}")

    slack_text = build_candidate_slack_text(cand)
    if args.send_slack:
        if not can_send_candidate_slack(explicit_cli=True):
            safe_print("[CANDIDATES] Slack 발송 차단 — --send-slack 필요")
        else:
            from slack_sender import post_buy_candidate_message

            posted = post_buy_candidate_message(slack_text, retries=1)
            safe_print(f"[CANDIDATES] slack_sent={posted.get('ok')}")
    else:
        safe_print("[CANDIDATES] slack (dry, 제안만):")
        safe_print(slack_text[:4000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
