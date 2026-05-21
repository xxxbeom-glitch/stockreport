"""MarketDataAgent — 관심종목 25개 장중 스냅샷 (더미 / KIS·pykrx 라이브)."""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Any

from data.kr_watchlist import iter_watchlist_entries

from .live_market_data import fetch_live_watchlist_row

logger = logging.getLogger("kr_intraday.market_data")


def _seed(ticker: str, slot: str) -> int:
    key = f"{date.today().isoformat()}:{slot}:{ticker}"
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def _fmt_won(value: int) -> str:
    return f"{value:,}원"


def _dummy_row(entry: dict[str, Any], slot: str) -> dict[str, Any]:
    ticker = entry["ticker"]
    seed = _seed(ticker, slot)
    base = 30_000 + (seed % 90_000)
    prev_close = int(base * (0.97 + (seed % 30) / 1000))
    current = int(base * (0.99 + (seed % 50) / 1000))
    day_high = int(max(current, current * (1.0 + (seed % 20) / 1000)))
    day_low = int(min(current, current * (0.98 - (seed % 15) / 1000)))
    high_52 = int(base * 1.15)
    vol_ratio = 0.8 + (seed % 120) / 100.0
    foreign_eok = (seed % 400) - 100
    inst_eok = (seed % 300) - 80
    pullback = (seed % 12) / 100.0
    return {
        "ticker": ticker,
        "name": entry["name"],
        "sector_key": entry["sector_key"],
        "sector_name": entry["sector_name"],
        "business": entry.get("business", ""),
        "selection_reason": entry.get("selection_reason", ""),
        "current_price": current,
        "current_price_fmt": _fmt_won(current),
        "prev_close": prev_close,
        "day_high": day_high,
        "day_low": day_low,
        "trading_value": int(base * vol_ratio * 1_000_000),
        "trading_value_fmt": _fmt_won(int(base * vol_ratio * 1_000_000)),
        "high_52w": high_52,
        "high_52w_fmt": _fmt_won(high_52),
        "pullback_from_high_pct": round(pullback, 2),
        "volume_ratio": round(vol_ratio, 2),
        "trading_value_vs_3m": round(vol_ratio * 0.9, 2),
        "foreign_net_eok": foreign_eok,
        "inst_net_eok": inst_eok,
        "target_price": int(base * 1.1),
        "target_price_fmt": _fmt_won(int(base * 1.1)),
        "news_headline": "",
        "data_complete": True,
        "live": False,
        "price_source": "dummy",
        "fetch_errors": [],
    }


def _normalize_live_row(row: dict[str, Any]) -> dict[str, Any]:
    """live_market_data 결과를 downstream 필드명에 맞춤."""
    out = dict(row)
    if out.get("foreign_net_eok") is None:
        out["foreign_net_eok"] = 0
    if out.get("inst_net_eok") is None:
        out["inst_net_eok"] = 0
    out.setdefault("news_headline", "")
    out.setdefault("volume_ratio", 0.0)
    out.setdefault("trading_value_vs_3m", out.get("volume_ratio"))
    return out


def collect_watchlist_market_data(
    slot: str,
    *,
    live: bool = False,
    tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    관심종목만 수집.
    - live=False: 결정적 더미
    - live=True: KIS/pykrx (실패 시 더미 대체 없음, 로그·fetch_errors)
    - tickers: 지정 시 해당 티커만 (테스트용)
    """
    allow = {str(t).zfill(6) for t in tickers} if tickers else None
    rows: list[dict[str, Any]] = []
    ok = 0
    fail = 0

    for entry in iter_watchlist_entries():
        ticker = str(entry.get("ticker", "")).zfill(6)
        if not ticker:
            logger.warning("[%s] watchlist 티커 없음 — 스킵", entry.get("name"))
            continue
        if allow is not None and ticker not in allow:
            continue

        if live:
            row = _normalize_live_row(fetch_live_watchlist_row(entry))
            if row.get("data_complete"):
                ok += 1
            else:
                fail += 1
            rows.append(row)
        else:
            rows.append(_dummy_row(entry, slot))

    if live:
        logger.info(
            "[KR INTRADAY] live 수집 완료 slot=%s total=%d ok=%d fail=%d",
            slot,
            len(rows),
            ok,
            fail,
        )
    return rows


def collect_sector_market_data(
    entries: list[dict[str, Any]],
    slot: str,
    *,
    live: bool = False,
) -> list[dict[str, Any]]:
    """섹터 소속 종목만 시세 수집 (병렬 섹터 스캔용)."""
    rows: list[dict[str, Any]] = []
    ok = 0
    fail = 0
    sector_name = entries[0].get("sector_name", "") if entries else ""

    for entry in entries:
        ticker = str(entry.get("ticker", "")).zfill(6)
        if not ticker:
            logger.warning("[%s] watchlist 티커 없음 — 스킵", entry.get("name"))
            continue
        if live:
            row = _normalize_live_row(fetch_live_watchlist_row(entry))
            if row.get("data_complete"):
                ok += 1
            else:
                fail += 1
            rows.append(row)
        else:
            rows.append(_dummy_row(entry, slot))

    if live and sector_name:
        logger.info(
            "[%s] live 수집 sector stocks=%d ok=%d fail=%d",
            sector_name,
            len(rows),
            ok,
            fail,
        )
    return rows
