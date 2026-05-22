# -*- coding: utf-8 -*-
"""DART 공시 감시 — 긴급 판단 후보 생성 (자동 가상매수 없음)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def fetch_disclosure_alerts(ticker: str) -> list[dict[str, Any]]:
    """종목별 최근 중요 공시 → intraday 후보 신호."""
    try:
        from data.dart_client import fetch_important_disclosure_items
    except Exception as exc:
        logger.debug("dart import failed: %s", exc)
        return []

    code = str(ticker).zfill(6)
    try:
        items = fetch_important_disclosure_items(code)
    except Exception as exc:
        logger.warning("[%s] DART fetch failed: %s", code, exc)
        return []

    alerts: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("report_nm") or "").strip()
        if not title:
            continue
        alerts.append(
            {
                "ticker": code,
                "signal_type": "dart_disclosure",
                "title": title,
                "reasons": [f"DART 공시: {title[:80]}"],
                "raw": item,
            }
        )
    return alerts[:5]
