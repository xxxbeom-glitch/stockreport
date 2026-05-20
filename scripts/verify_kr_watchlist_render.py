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
    "조선·해양방산·해운",
]


class VerifyError(Exception):
    """검증 실패."""


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


def run_verify() -> dict[str, Any]:
    """검증 실행. 성공 시 요약 dict, 실패 시 VerifyError."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

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
        "error": None,
    }

    env = {**os.environ, "KR_MARKET_OFFLINE": "1", "PYTHONUTF8": "1"}
    print("[KR WATCHLIST] render: python template/kr_market/render.py")
    try:
        subprocess.run(
            [sys.executable, str(RENDER_SCRIPT)],
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
        result["error"] = f"render.py 종료 코드 {exc.returncode}"
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
    if not isinstance(watchlist_stocks, list) or len(watchlist_stocks) < 1:
        result["error"] = "watchlistStocks가 비어 있음"
        raise VerifyError(result["error"])
    result["watchlist_stocks_ok"] = True
    result["stocks"] = len(watchlist_stocks)

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

    na_in_report = any(
        str(row.get("current_price", "")) == "N/A"
        or str(row.get("target_price", "")) == "N/A"
        or str(row.get("foreign_net_buy", "")) == "N/A"
        or str(row.get("high_52w", "")) == "N/A"
        for row in watchlist_stocks
        if isinstance(row, dict)
    )
    na_in_html = ">N/A<" in html or ">N/A</" in html
    if not (na_in_report and na_in_html):
        result["error"] = "N/A 필드 렌더링 확인 실패"
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
    print(f"[KR WATCHLIST] sectors: {result.get('sectors')}")
    print(f"[KR WATCHLIST] stocks: {result.get('stocks')}")
    print("[KR WATCHLIST] labels: 안 사면 후회함 / 지금 사기엔 좀...")
    print("[KR WATCHLIST] render: OK" if result.get("render_ok") else "[KR WATCHLIST] render: FAIL")
    print("[KR WATCHLIST] dropdown sectors: OK (5)")
    print("[KR WATCHLIST] N/A fields: OK")


def _notify_slack(result: dict[str, Any]) -> None:
    from slack_sender import send_kr_watchlist_verify_slack

    slack_result = send_kr_watchlist_verify_slack(result)
    if slack_result.get("skipped"):
        print("[KR WATCHLIST] Slack skipped:", slack_result.get("error"), file=sys.stderr)
        sys.exit(1)
    if not slack_result.get("ok"):
        print("[KR WATCHLIST] Slack FAIL:", slack_result.get("error"), file=sys.stderr)
        sys.exit(1)
    print("[KR WATCHLIST] Slack: OK")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="KR watchlist render 검증")
    parser.add_argument(
        "--notify-slack",
        action="store_true",
        help="검증 성공 후 SLACK_BOT_TOKEN + SLACK_CHANNEL_KR 로 알림",
    )
    args = parser.parse_args()

    try:
        summary = run_verify()
        _print_summary(summary)
        if args.notify_slack:
            _notify_slack(summary)
    except VerifyError as exc:
        print(f"[KR WATCHLIST] FAIL: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
