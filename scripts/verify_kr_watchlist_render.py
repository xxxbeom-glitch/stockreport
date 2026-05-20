#!/usr/bin/env python3
"""KR watchlist + kr_market render 검증 (GitHub Actions 로그용)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

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


def _fail(msg: str) -> None:
    print(f"[KR WATCHLIST] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _extract_report_data(html: str) -> dict:
    marker = "window.reportData = "
    start = html.find(marker)
    if start < 0:
        _fail("index.html에 window.reportData 없음")
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
                    _fail(f"reportData JSON 파싱 실패: {exc}")
    _fail("reportData JSON 경계를 찾지 못함")


def _stock_filter_options(html: str) -> list[str]:
    block_m = re.search(
        r'<select[^>]*id="stock-filter"[^>]*>(.*?)</select>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not block_m:
        _fail('id="stock-filter" select 없음')
    return re.findall(r'<option\s+value="([^"]*)"', block_m.group(1))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

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
    except subprocess.CalledProcessError as exc:
        print(exc.stdout or "", file=sys.stderr)
        print(exc.stderr or "", file=sys.stderr)
        _fail(f"render.py 종료 코드 {exc.returncode}")

    if not INDEX_HTML.is_file():
        _fail(f"index.html 미생성: {INDEX_HTML}")

    html = INDEX_HTML.read_text(encoding="utf-8")
    report_data = _extract_report_data(html)

    if "watchlistStocks" not in report_data:
        _fail("reportData.watchlistStocks 없음")
    watchlist_stocks = report_data["watchlistStocks"]
    if not isinstance(watchlist_stocks, list) or len(watchlist_stocks) < 1:
        _fail("watchlistStocks가 비어 있음")

    meta = report_data.get("meta") or {}
    if "watchlistSectors" not in meta:
        _fail("reportData.meta.watchlistSectors 없음")
    sectors = meta["watchlistSectors"]
    if not isinstance(sectors, list) or len(sectors) != 5:
        _fail(f"watchlistSectors 개수 오류 (기대 5, 실제 {len(sectors) if isinstance(sectors, list) else type(sectors)})")

    labels = meta.get("labels")
    if labels != EXPECTED_LABELS:
        _fail(f"meta.labels 불일치: {labels!r} (기대 {EXPECTED_LABELS!r})")

    filter_opts = _stock_filter_options(html)
    sector_opts = [o for o in filter_opts if o != "전체섹터"]
    if sector_opts != EXPECTED_SECTOR_OPTIONS:
        _fail(
            f"드롭다운 섹터 옵션 불일치\n  기대: {EXPECTED_SECTOR_OPTIONS}\n  실제: {sector_opts}"
        )

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
        _fail("N/A 필드 렌더링 확인 실패 (reportData 또는 HTML)")

    for row in watchlist_stocks:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", ""))
        if label and label not in EXPECTED_LABELS:
            _fail(f"허용되지 않은 라벨: {label!r}")

    print(f"[KR WATCHLIST] sectors: {len(sectors)}")
    print(f"[KR WATCHLIST] stocks: {len(watchlist_stocks)}")
    print("[KR WATCHLIST] labels: 안 사면 후회함 / 지금 사기엔 좀...")
    print("[KR WATCHLIST] render: OK")
    print("[KR WATCHLIST] dropdown sectors: OK (5)")
    print("[KR WATCHLIST] N/A fields: OK")


if __name__ == "__main__":
    main()
