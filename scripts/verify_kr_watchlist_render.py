#!/usr/bin/env python3
"""KR watchlist + kr_market render 검증 (GitHub Actions 로그·Slack 알림)."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "template" / "kr_market" / "index.html"
RENDER_SCRIPT = ROOT / "template" / "kr_market" / "render.py"

EXPECTED_LABELS = ["안 사면 후회함", "지금 사기엔 좀..."]
EXPECTED_SECTOR_OPTIONS = [
    "반도체 소재",
    "반도체 부품",
    "반도체 장비",
    "방산·우주",
    "조선·기자재",
]


class VerifyError(Exception):
    """검증 실패."""


def _expected_stock_count() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from data.kr_watchlist import watchlist_stock_count

    return watchlist_stock_count()


def _extract_report_data(html: str) -> dict[str, Any]:
    marker = "window.reportData = "
    start = html.find(marker)
    if start < 0:
        raise VerifyError("index.html에 window.reportData 없음")
    start += len(marker)
    depth = 0
    in_str = False
    escape = False
    quote = ""
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : i + 1])
                except json.JSONDecodeError as exc:
                    raise VerifyError(f"reportData JSON 파싱 실패: {exc}") from exc
    raise VerifyError("reportData JSON 경계를 찾지 못함")


def _stock_filter_options(html: str) -> list[str]:
    block_m = re.search(
        r'<select[^>]*id="stock-filter"[^>]*>(.*?)</select>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not block_m:
        raise VerifyError('id="stock-filter" select 없음')
    return re.findall(r'<option\s+value="([^"]*)"', block_m.group(1))


def _count_stock_cards(html: str) -> int:
    return len(re.findall(r'<article[^>]*class="[^"]*stock-card', html))


def run_verify() -> dict[str, Any]:
    """검증 실행. data/kr_watchlist.json 전체 기준."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    expected_stocks = _expected_stock_count()
    result: dict[str, Any] = {
        "ok": False,
        "render_ok": False,
        "index_html_ok": False,
        "watchlist_stocks_ok": False,
        "watchlist_sectors_ok": False,
        "labels_ok": False,
        "labels_text": "안 사면 후회함 / 지금 사기엔 좀...",
        "sectors": 0,
        "stocks": 0,
        "expected_stocks": expected_stocks,
        "source": "data/kr_watchlist.json",
        "error": None,
    }

    env = {**os.environ, "KR_MARKET_OFFLINE": "1", "PYTHONUTF8": "1"}
    print(f"[KR WATCHLIST] source: data/kr_watchlist.json ({expected_stocks} stocks)")
    print("[KR WATCHLIST] render: python template/kr_market/render.py --verify")
    try:
        subprocess.run(
            [sys.executable, str(RENDER_SCRIPT), "--verify"],
            cwd=str(ROOT),
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        result["render_ok"] = True
    except subprocess.CalledProcessError as exc:
        print(exc.stdout or "", file=sys.stderr)
        print(exc.stderr or "", file=sys.stderr)
        result["error"] = f"render.py --verify 종료 코드 {exc.returncode}"
        raise VerifyError(result["error"]) from exc

    if not INDEX_HTML.is_file():
        result["error"] = f"index.html 미생성: {INDEX_HTML}"
        raise VerifyError(result["error"])

    result["index_html_ok"] = True
    html = INDEX_HTML.read_text(encoding="utf-8")
    report_data = _extract_report_data(html)

    if "watchlistStocks" not in report_data:
        result["error"] = "reportData.watchlistStocks 없음"
        raise VerifyError(result["error"])
    watchlist_stocks = report_data["watchlistStocks"]
    if not isinstance(watchlist_stocks, list):
        result["error"] = "watchlistStocks 타입 오류"
        raise VerifyError(result["error"])
    result["stocks"] = len(watchlist_stocks)
    if result["stocks"] != expected_stocks:
        result["error"] = (
            f"watchlistStocks 개수 오류 (기대 {expected_stocks}, 실제 {result['stocks']})"
        )
        raise VerifyError(result["error"])
    result["watchlist_stocks_ok"] = True

    card_count = _count_stock_cards(html)
    if card_count != expected_stocks:
        result["error"] = f"HTML stock-card 개수 오류 (기대 {expected_stocks}, 실제 {card_count})"
        raise VerifyError(result["error"])

    meta = report_data.get("meta") or {}
    if "watchlistSectors" not in meta:
        result["error"] = "reportData.meta.watchlistSectors 없음"
        raise VerifyError(result["error"])
    sectors = meta["watchlistSectors"]
    if not isinstance(sectors, list) or len(sectors) != 5:
        result["error"] = f"watchlistSectors 개수 오류 (기대 5, 실제 {len(sectors) if isinstance(sectors, list) else type(sectors)})"
        raise VerifyError(result["error"])
    result["watchlist_sectors_ok"] = True
    result["sectors"] = len(sectors)

    labels = meta.get("labels")
    result["labels_ok"] = labels == EXPECTED_LABELS
    if not result["labels_ok"]:
        result["error"] = f"meta.labels 불일치: {labels!r}"
        raise VerifyError(result["error"])

    filter_opts = _stock_filter_options(html)
    sector_opts = [o for o in filter_opts if o != "전체섹터"]
    if sector_opts != EXPECTED_SECTOR_OPTIONS:
        result["error"] = f"드롭다운 섹터 옵션 불일치: {sector_opts}"
        raise VerifyError(result["error"])

    forbidden = ("해운", "HMM", "팬오션", "조선·해양방산·해운")
    if any(token in html for token in forbidden):
        result["error"] = f"제외 섹터/종목 문자열 포함: {[t for t in forbidden if t in html]}"
        raise VerifyError(result["error"])

    missing_price = [
        str(row.get("name", ""))
        for row in watchlist_stocks
        if isinstance(row, dict)
        and str(row.get("current_price", "")).strip() in ("", "N/A")
    ]
    if missing_price:
        result["error"] = f"current_price 미기재: {missing_price[:3]}"
        raise VerifyError(result["error"])

    if "선정이유" not in html:
        result["error"] = "선정이유 섹션 미렌더"
        raise VerifyError(result["error"])

    for row in watchlist_stocks:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", ""))
        if label and label not in EXPECTED_LABELS:
            result["error"] = f"허용되지 않은 라벨: {label!r}"
            raise VerifyError(result["error"])

    result["ok"] = True
    return result


def _print_summary(result: dict[str, Any]) -> None:
    print(f"[KR WATCHLIST] render: {'OK' if result.get('render_ok') else 'FAIL'}")
    print(f"[KR WATCHLIST] index.html: {'OK' if result.get('index_html_ok') else 'FAIL'}")
    print(
        "[KR WATCHLIST] reportData.watchlistStocks: "
        f"{'OK' if result.get('watchlist_stocks_ok') else 'FAIL'}"
    )
    print(f"[KR WATCHLIST] sectors: {result.get('sectors')}")
    print(f"[KR WATCHLIST] stocks: {result.get('stocks')}")
    print("[KR WATCHLIST] labels: 안 사면 후회함 / 지금 사기엔 좀...")
    print("[KR WATCHLIST] dropdown sectors: OK (5)")
    print("[KR WATCHLIST] fixed pool (no shipping): OK")
    if "firebase_ok" in result:
        print(f"[KR WATCHLIST] firebase upload: {'OK' if result.get('firebase_ok') else 'FAIL'}")
    if result.get("briefing_url"):
        print(f"[KR WATCHLIST] briefing_url: {result['briefing_url']}")
    if "slack_ok" in result:
        print(f"[KR WATCHLIST] slack: {'OK' if result.get('slack_ok') else 'FAIL'}")


def _upload_index_to_firebase() -> dict[str, Any]:
    """기존 firebase_client.save_report — 국장 브리핑과 동일."""
    from datetime import datetime

    from firebase_client import save_report

    filename = f"{datetime.now().strftime('%y%m%d_%H%M')}_kr_watchlist.html"
    return save_report(
        payload={
            "report_data": {
                "report_type": "kr_during",
                "one_line_summary": "KR 관심종목 watchlist 리포트",
            },
            "file_path": str(INDEX_HTML),
            "report_type": "kr_during",
            "filename": filename,
        }
    )


def _notify_slack(result: dict[str, Any]) -> None:
    import config

    if not config.legacy_report_slack_enabled():
        print(
            "[KR WATCHLIST] --notify-slack skipped (legacy_report_slack_disabled). "
            "Set STOCKREPORT_ALLOW_LEGACY_REPORT_SLACK=1 to enable.",
            file=sys.stderr,
        )
        return

    from slack_sender import send_kr_watchlist_report_slack

    fb = _upload_index_to_firebase()
    briefing_url = str(fb.get("url") or "")
    result["firebase_ok"] = bool(briefing_url)
    result["briefing_url"] = briefing_url
    if not briefing_url:
        err = fb.get("firebase_init_error") or fb.get("firestore_error") or "upload returned empty url"
        print(f"[KR WATCHLIST] Firebase WARN: {err}", file=sys.stderr)
        if not fb.get("firebase_init_ok"):
            sys.exit(1)

    slack_result = send_kr_watchlist_report_slack(result, briefing_url, report_type="kr_during")
    result["slack_ok"] = bool(slack_result.get("ok"))
    if not slack_result.get("ok"):
        errs = slack_result.get("errors") or ["unknown"]
        print("[KR WATCHLIST] Slack FAIL:", "; ".join(errs), file=sys.stderr)
        sys.exit(1)
    print("[KR WATCHLIST] Slack: OK")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="KR watchlist render 검증 (kr_watchlist.json 전체)")
    parser.add_argument(
        "--notify-slack",
        action="store_true",
        help="검증 성공 후 SLACK_BOT_TOKEN + SLACK_CHANNEL_KR 로 알림",
    )
    args = parser.parse_args()

    try:
        summary = run_verify()
        if args.notify_slack:
            _notify_slack(summary)
        _print_summary(summary)
    except VerifyError as exc:
        print(f"[KR WATCHLIST] FAIL: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
