"""KR 관심 섹터·종목 watchlist (kr_market 관심 종목 투자의견)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

_WATCHLIST_PATH = Path(__file__).resolve().parent / "kr_watchlist.json"

# 섹터 표시·필터 순서 (고정)
SECTOR_ORDER: tuple[str, ...] = (
    "semiconductor_subdev",
    "aerospace_defense",
    "shipbuilding_robotics",
)

FILTER_ALL = "전체섹터"

WATCHLIST_STOCK_LIMIT = 29
WATCHLIST_SECTOR_LIMIT = 3
FORBIDDEN_SECTOR_KEYWORDS: tuple[str, ...] = ("해운", "조선·해양방산·해운")


@lru_cache(maxsize=1)
def load_kr_watchlist_raw() -> dict[str, Any]:
    with _WATCHLIST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_kr_watchlist_raw(
    data: dict[str, Any],
    *,
    explicit_apply: bool = False,
) -> bool:
    """
    kr_watchlist.json 저장. explicit_apply + WATCHLIST_AUTO_APPLY 게이트 통과 시에만 기록.
    """
    from utils.safe_mode import can_apply_watchlist

    if not can_apply_watchlist(explicit_cli=explicit_apply):
        return False
    _WATCHLIST_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    load_kr_watchlist_raw.cache_clear()
    return True


def watchlist_sectors_meta() -> list[dict[str, Any]]:
    """reportData.meta.watchlistSectors."""
    raw = load_kr_watchlist_raw()
    sectors = raw.get("sectors") or {}
    out: list[dict[str, Any]] = []
    for idx, key in enumerate(SECTOR_ORDER):
        block = sectors.get(key) or {}
        out.append(
            {
                "sector_key": key,
                "sector_name": str(block.get("label", key)),
                "order": idx,
            }
        )
    return out


def stock_filter_options() -> list[str]:
    """드롭다운: 전체 + 섹터명."""
    labels = [str((load_kr_watchlist_raw().get("sectors") or {}).get(k, {}).get("label", k)) for k in SECTOR_ORDER]
    return [FILTER_ALL, *labels]


def _normalize_ticker(ticker: str | None) -> str:
    t = str(ticker or "").strip()
    if not t:
        return ""
    if t.isdigit():
        return t.zfill(6)
    return t.upper()


def _resolve_ticker_by_name(name: str) -> str:
    """종목명 → 티커 (pykrx, 실패 시 빈 문자열)."""
    name = str(name).strip()
    if not name:
        return ""
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        from data.kr_market import get_trading_date

        date = get_trading_date()
        for market in ("KOSPI", "KOSDAQ", "KONEX"):
            try:
                tickers = pykrx_stock.get_market_ticker_list(date, market=market)
            except Exception:
                continue
            for t in tickers:
                code = str(t).zfill(6)
                try:
                    nm = str(pykrx_stock.get_market_ticker_name(code)).strip()
                except Exception:
                    continue
                if nm == name:
                    return code
    except Exception:
        pass
    return ""


def iter_watchlist_entries(*, resolve_missing_tickers: bool = False) -> Iterator[dict[str, Any]]:
    """
    Yield flat watchlist rows:
    sector_key, sector_name, name, ticker, sector_order, stock_order.
    """
    raw = load_kr_watchlist_raw()
    sectors = raw.get("sectors") or {}
    for sector_order, sector_key in enumerate(SECTOR_ORDER):
        block = sectors.get(sector_key) or {}
        sector_name = str(block.get("label", sector_key))
        stocks = block.get("stocks") or []
        for stock_order, item in enumerate(stocks):
            business = ""
            selection_reason = ""
            if isinstance(item, str):
                name = item.strip()
                ticker = ""
            else:
                name = str(item.get("name", "")).strip()
                ticker = _normalize_ticker(item.get("ticker"))
                business = str(item.get("business", "")).strip()
                selection_reason = str(item.get("selection_reason", "")).strip()
            if resolve_missing_tickers and not ticker and name:
                ticker = _resolve_ticker_by_name(name)
            yield {
                "sector_key": sector_key,
                "sector_name": sector_name,
                "name": name or "UNKNOWN",
                "ticker": ticker,
                "business": business,
                "selection_reason": selection_reason,
                "sector_order": sector_order,
                "stock_order": stock_order,
            }


def watchlist_stock_count() -> int:
    """관심종목 총 개수 (data/kr_watchlist.json)."""
    return sum(1 for _ in iter_watchlist_entries())


def watchlist_ticker_set() -> set[str]:
    """관심종목 티커 집합 (6자리)."""
    return {e["ticker"] for e in iter_watchlist_entries() if e.get("ticker")}


def watchlist_sector_labels() -> list[str]:
    """섹터 표시명 (SECTOR_ORDER)."""
    raw = load_kr_watchlist_raw()
    sectors = raw.get("sectors") or {}
    return [str((sectors.get(k) or {}).get("label", k)) for k in SECTOR_ORDER]


def default_sector_flow() -> dict[str, list[str]]:
    """관심 섹터 기준 hot/cold (오프라인·검증용)."""
    labels = watchlist_sector_labels()
    if len(labels) >= 3:
        return {"hot": labels[:2], "cold": [labels[-1]]}
    return {"hot": labels, "cold": []}


def kr_watchlist_theme_map() -> dict[str, dict[str, str]]:
    """config.KR_WATCHLIST 호환: 섹터명 → {ticker: name}."""
    out: dict[str, dict[str, str]] = {}
    for entry in iter_watchlist_entries():
        theme = entry["sector_name"]
        ticker = entry["ticker"]
        if not ticker:
            continue
        out.setdefault(theme, {})[ticker] = entry["name"]
    return out


def validate_watchlist_spec() -> list[str]:
    """01_watchlist.md 기준 검증. 문제 없으면 빈 리스트."""
    errors: list[str] = []
    raw = load_kr_watchlist_raw()
    sectors = raw.get("sectors") or {}
    if len(SECTOR_ORDER) != WATCHLIST_SECTOR_LIMIT:
        errors.append(f"SECTOR_ORDER 개수: {len(SECTOR_ORDER)} (기대 {WATCHLIST_SECTOR_LIMIT})")
    count = watchlist_stock_count()
    if count != WATCHLIST_STOCK_LIMIT:
        errors.append(f"종목 수: {count} (기대 {WATCHLIST_STOCK_LIMIT})")
    for key in SECTOR_ORDER:
        if key not in sectors:
            errors.append(f"섹터 키 누락: {key}")
    for key, block in sectors.items():
        label = str(block.get("label", ""))
        if any(kw in label for kw in FORBIDDEN_SECTOR_KEYWORDS):
            errors.append(f"금지 섹터 라벨: {label}")
        for item in block.get("stocks") or []:
            if isinstance(item, dict):
                nm = str(item.get("name", ""))
                if any(kw in nm for kw in ("HMM", "팬오션")):
                    errors.append(f"금지 종목: {nm}")
    return errors


def filter_rows_to_watchlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """관심종목 풀 밖 항목 제거."""
    allowed = watchlist_ticker_set()
    if not allowed:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        t = _normalize_ticker(str(row.get("ticker", "")))
        if t and t in allowed:
            out.append(row)
    return out


def _pipeline_index(pipeline: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    if not pipeline:
        return idx
    for src in (
        ((pipeline.get("watchlist_data") or {}).get("stocks") or []),
        (pipeline.get("supply") or {}).get("filtered_stocks") or [],
    ):
        for row in src:
            if not isinstance(row, dict):
                continue
            t = _normalize_ticker(str(row.get("ticker", "")))
            if t:
                idx[t] = {**row, "ticker": t}
    return idx


def build_watchlist_stock_pool(
    pipeline: dict[str, Any] | None = None,
    *,
    resolve_missing_tickers: bool = False,
) -> list[dict[str, Any]]:
    """Merge static watchlist with pipeline metrics for _build_stock_row."""
    pipe_idx = _pipeline_index(pipeline)
    pool: list[dict[str, Any]] = []
    for entry in iter_watchlist_entries(resolve_missing_tickers=resolve_missing_tickers):
        ticker = entry["ticker"]
        merged: dict[str, Any] = {
            "ticker": ticker,
            "name": entry["name"],
            "market": "KOSPI",
            "theme": entry["sector_name"],
            "sector_key": entry["sector_key"],
            "sector_name": entry["sector_name"],
            "sector_order": entry["sector_order"],
            "stock_order": entry["stock_order"],
            "business": entry.get("business", ""),
            "selection_reason": entry.get("selection_reason", ""),
        }
        if ticker and ticker in pipe_idx:
            merged.update({k: v for k, v in pipe_idx[ticker].items() if v is not None})
            merged["name"] = entry["name"] or pipe_idx[ticker].get("name") or entry["name"]
            merged["sector_key"] = entry["sector_key"]
            merged["sector_name"] = entry["sector_name"]
        pool.append(merged)
    return pool


def _label_sort_key(row: dict[str, Any]) -> int:
    label = str(row.get("label") or row.get("verdict") or row.get("verdict_badge") or "")
    if "후회" in label:
        return 0
    return 1


def sort_kr_focus_stocks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """섹터 순서 → 라벨(안 사면 후회함 우선)."""
    return sorted(
        rows,
        key=lambda r: (
            int(r.get("sector_order", 99)),
            int(r.get("stock_order", 99)),
            _label_sort_key(r),
            str(r.get("name", "")),
        ),
    )
