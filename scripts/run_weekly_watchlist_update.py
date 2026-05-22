#!/usr/bin/env python3
"""주간 관심종목 25개 재평가 (MVP 1단계)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.safe_stdio import ensure_stdio, safe_print, setup_logging  # noqa: E402

from agents.kr_intraday_slack.llm_client import (  # noqa: E402
    aux_models_status,
    is_primary_configured,
)
from agents.weekly_watchlist_update import run_weekly_watchlist_update  # noqa: E402
from data.kr_watchlist import load_kr_watchlist_raw, validate_watchlist_spec  # noqa: E402
from utils.safe_mode import (  # noqa: E402
    can_send_watchlist_review_slack,
    print_watchlist_review_status,
)


def main() -> int:
    ensure_stdio()
    setup_logging()

    parser = argparse.ArgumentParser(description="주간 관심종목 재평가 (MVP 1)")
    parser.add_argument("--as-of", default=None, help="기준일 YYYY-MM-DD (기본: 최근 거래일)")
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Slack 미발송 (기본)",
    )
    parser.add_argument(
        "--send-slack",
        "--send",
        action="store_true",
        dest="send_slack",
        help="관심종목 새벽 리포트 Slack 발송 (WATCHLIST_REVIEW_AUTO_SEND=true 필요)",
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Actions schedule 실행 (새벽 자동 발송)",
    )
    parser.add_argument(
        "--apply-watchlist",
        action="store_true",
        help="제안서를 kr_watchlist.json에 반영 (WATCHLIST_AUTO_APPLY=true 필요)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="DeepSeek 없이 규칙만",
    )
    parser.add_argument("--json", action="store_true", help="JSON 요약 stdout")
    parser.add_argument(
        "--slack-log-days",
        type=int,
        default=7,
        help="장중 Slack 로그 집계 일수",
    )
    parser.add_argument(
        "--pykrx-only",
        action="store_true",
        help="KIS snapshot 생략 (pykrx OHLCV만, 빠른 드라이런)",
    )
    parser.add_argument(
        "--with-news",
        action="store_true",
        help="네이버 뉴스·DART 공시 수집 (data/news/stock_news_YYYY-MM-DD.json)",
    )
    parser.add_argument(
        "--use-existing-news",
        action="store_true",
        help="API 없이 data/news/stock_news_YYYY-MM-DD.json 만 로드·연결",
    )
    parser.add_argument(
        "--with-candidates",
        action="store_true",
        help="watchlist 제외·섹터 유니버스에서 새 후보 스캔 (제안만, watchlist 미수정)",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=60,
        metavar="N",
        help="후보 pykrx 스캔 상한 (섹터 우선순위 상위 N, 기본 60)",
    )
    parser.add_argument(
        "--candidate-days",
        type=int,
        default=5,
        metavar="N",
        help="daily_scan 누적 일수·trend_score 윈도 (기본 5)",
    )
    args = parser.parse_args()

    print_watchlist_review_status(emit=safe_print)

    send = (
        args.send_slack
        and not args.no_send
        and can_send_watchlist_review_slack(
            explicit_cli=bool(args.send_slack),
            scheduled=bool(args.scheduled),
        )
    )
    spec_errs = validate_watchlist_spec()
    if spec_errs:
        safe_print("[WEEKLY] watchlist 검증 실패:", spec_errs)
        return 2

    deepseek_configured = is_primary_configured()
    if args.no_llm:
        llm_mode = "rule_only (--no-llm, API 호출 없음)"
    elif deepseek_configured:
        llm_mode = "deepseek (판단 시 1회 호출)"
    else:
        llm_mode = "rule_fallback (API 키 없음)"

    safe_print(f"[WEEKLY] DeepSeek configured: {deepseek_configured}")
    safe_print(f"[WEEKLY] LLM run mode: {llm_mode}")
    if not args.no_llm:
        safe_print(f"[WEEKLY] aux (참고, 주간 파이프라인 미사용): {aux_models_status()}")

    watchlist_before = None
    if args.apply_watchlist:
        watchlist_before = load_kr_watchlist_raw()

    result = run_weekly_watchlist_update(
        as_of_date=args.as_of,
        send_slack=send,
        send_slack_explicit=bool(args.send_slack),
        apply_watchlist=bool(args.apply_watchlist),
        use_llm=not args.no_llm,
        slack_log_days=args.slack_log_days,
        fetch_snapshots=not args.pykrx_only,
        collect_news=args.with_news,
        use_existing_news=args.use_existing_news,
    )

    if watchlist_before is not None:
        watchlist_after = load_kr_watchlist_raw()
        if watchlist_before == watchlist_after:
            safe_print("[WEEKLY] watchlist unchanged (proposal only or apply blocked)")
        else:
            safe_print("[WEEKLY] watchlist updated via --apply-watchlist")

    safe_print(f"[WEEKLY] as_of={result.as_of_date} stocks={len(result.metrics)}")
    safe_print(
        f"[WEEKLY] LLM invoked: {bool(result.judgment.get('llm_used'))}"
    )
    safe_print(
        f"[WEEKLY] keep={result.judgment.get('keep_count')} "
        f"weaken={result.judgment.get('weaken_count')} "
        f"caution={result.judgment.get('caution_count', 0)} "
        f"remove={result.judgment.get('remove_count')} "
        f"(strong={result.judgment.get('strong_remove_count', 0)} "
        f"review={result.judgment.get('review_remove_count', 0)}) "
        f"data_check={result.judgment.get('data_check_count')}"
    )
    status_counts: dict[str, int] = {}
    for row in result.metrics:
        st = str(row.get("data_status") or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1
    safe_print(f"[WEEKLY] data_status: {status_counts}")
    missing = [
        f"{r.get('symbol')}({r.get('ticker')})"
        for r in result.metrics
        if r.get("data_status") == "missing_ohlcv"
    ]
    if missing:
        safe_print(f"[WEEKLY] missing_ohlcv ({len(missing)}): {', '.join(missing)}")
    if result.report_path:
        safe_print(f"[WEEKLY] report: {result.report_path}")
    if result.proposal_path:
        safe_print(f"[WEEKLY] proposal: {result.proposal_path}")
    if result.news_path:
        safe_print(f"[WEEKLY] stock_news: {result.news_path}")
    elif args.with_news:
        safe_print("[WEEKLY] stock_news: (저장 실패 또는 미수집)")
    if args.use_existing_news and not args.with_news:
        safe_print("[WEEKLY] news: use-existing-news (API 수집 없음)")
    if result.judgment.get("news_with_issue_count") is not None:
        safe_print(
            f"[WEEKLY] news attached issue="
            f"{result.judgment.get('news_with_issue_count', 0)}/"
            f"{len(result.metrics)}"
        )
    if result.errors:
        safe_print("[WEEKLY] errors:", result.errors)
    if send:
        safe_print(f"[WEEKLY] slack_sent={result.slack_sent}")
    else:
        safe_print("[WEEKLY] slack (dry):")
        safe_print(result.slack_text[:2000])

    if args.with_candidates:
        from agents.weekly_watchlist_update.candidate_report import (
            build_candidate_slack_text,
            write_candidate_outputs,
        )
        from agents.weekly_watchlist_update.candidate_scanner import (
            format_candidate_scan_log_lines,
            run_candidate_scan,
        )

        limit = max(1, int(args.candidate_limit))
        trend_days = max(1, int(args.candidate_days))
        safe_print(
            f"[CANDIDATES] 신규 후보 스캔 시작 "
            f"(limit={limit}, trend_days={trend_days}, watchlist 제외·제안만)"
        )
        try:
            cand = run_candidate_scan(
                as_of_date=result.as_of_date,
                scan_limit=limit,
                candidate_days=trend_days,
                on_progress=safe_print,
            )
            cand_path = write_candidate_outputs(cand)
            cand_slack = build_candidate_slack_text(cand)
            for line in format_candidate_scan_log_lines(cand):
                safe_print(line)
            if cand_path:
                safe_print(f"[CANDIDATES] saved: {cand_path}")
            if cand.errors:
                safe_print("[CANDIDATES] errors:", cand.errors)
            safe_print("[CANDIDATES] slack (dry):")
            safe_print(cand_slack[:4000])
        except Exception as exc:
            safe_print(f"[CANDIDATES] 실패: {exc}")
            return 1

    if args.json:
        safe_print(
            json.dumps(
                {
                    "as_of_date": result.as_of_date,
                    "sector_mood": result.sector_mood,
                    "judgment_summary": result.judgment.get("summary"),
                    "top_keep": result.judgment.get("top_keep"),
                    "remove_candidates": result.judgment.get("remove_candidates"),
                    "weaken_list": result.judgment.get("weaken_list"),
                    "data_check_needed": result.judgment.get("data_check_needed"),
                    "llm_used": result.judgment.get("llm_used"),
                    "errors": result.errors,
                    "paths": {
                        "report": str(result.report_path) if result.report_path else None,
                        "proposal": str(result.proposal_path) if result.proposal_path else None,
                        "stock_news": str(result.news_path) if result.news_path else None,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    return 0 if result.metrics and not any("metrics:" in e for e in result.errors) else 1


if __name__ == "__main__":
    raise SystemExit(main())
