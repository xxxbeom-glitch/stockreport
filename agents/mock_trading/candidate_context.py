# -*- coding: utf-8 -*-
"""후보 종목 분석 데이터(가격·수급·뉴스·공시) 보강."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def enrich_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_enrich: int = 0,
    skip_news: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    metrics·news·disclosure 보강.
    max_enrich=0 이면 전체, dry-run에서는 skip_news=True 권장.
    """
    notes: list[str] = []
    if not candidates:
        return [], ["후보 없음"]

    targets = candidates if max_enrich <= 0 else candidates[:max_enrich]

    try:
        from agents.weekly_watchlist_update.weekly_metrics import (
            compute_stock_metrics,
            fetch_ohlcv_history,
        )
    except Exception as exc:
        notes.append(f"weekly_metrics import 실패: {type(exc).__name__}")
        return candidates, notes

    for row in targets:
        ticker = str(row.get("ticker", "")).zfill(6)
        try:
            ohlcv_rows, _meta = fetch_ohlcv_history(ticker, market="KOSDAQ")
            sector = row.get("sector_group") or (
                (row.get("sector_keys") or [None])[0]
            )
            metrics_row = {
                "ticker": ticker,
                "symbol": row.get("name"),
                "sector": sector,
            }
            computed = compute_stock_metrics(metrics_row, ohlcv_rows)
            m = row.setdefault("metrics", {})
            m["return_5d_pct"] = computed.get("return_5d")
            m["return_10d_pct"] = computed.get("return_10d")
            m["volume_change"] = computed.get("volume_ratio")
            m["trading_value_change"] = computed.get("tv_5d_avg")
            from agents.mock_trading.universe_builder import _trading_values_from_ohlcv

            avg_5d, last_tv = _trading_values_from_ohlcv(ohlcv_rows)
            m["avg_trading_value_5d"] = avg_5d
            m["last_trading_value"] = last_tv
            m["foreign_flow"] = None
            m["institution_flow"] = None
            notes.append(f"{ticker}: metrics OK")
        except Exception as exc:
            notes.append(f"{ticker}: metrics 실패 {type(exc).__name__}")

    if skip_news:
        notes.append("dry-run: 뉴스/공시 수집 생략")
        return candidates, notes

    try:
        from data.dart_client import fetch_important_disclosure_items, is_dart_configured
        from data.naver_news_client import is_naver_news_configured
        from agents.weekly_watchlist_update.news_collect import collect_naver_news_for_stock
    except Exception as exc:
        notes.append(f"뉴스/공시 모듈 import 실패: {type(exc).__name__}")
        return candidates, notes

    if not is_naver_news_configured():
        notes.append("네이버 뉴스 API 미설정 — news_context 비움")
    if not is_dart_configured():
        notes.append("DART API 미설정 — disclosure_context 비움")

    for row in targets:
        ticker = str(row.get("ticker", "")).zfill(6)
        name = str(row.get("name") or ticker)

        if is_naver_news_configured():
            try:
                news = collect_naver_news_for_stock(name, ticker, days=14, top_n=3)
                row["news_context"] = news[:3] if isinstance(news, list) else []
            except Exception as exc:
                notes.append(f"{ticker}: news 실패 {type(exc).__name__}")

        if is_dart_configured():
            try:
                items = fetch_important_disclosure_items(ticker, days=30, top_n=3)
                row["disclosure_context"] = items[:3] if isinstance(items, list) else []
            except Exception as exc:
                notes.append(f"{ticker}: dart 실패 {type(exc).__name__}")

    return candidates, notes
