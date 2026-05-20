"""KR 관심종목 Slack 알림 (v2 포맷 — agents.kr_intraday_slack 위임)."""

from __future__ import annotations

from typing import Any

from agents.kr_intraday_slack.constants import SLACK_SEND_ALLOWED
from agents.kr_intraday_slack.slack_message import build_slack_message
from data.kr_watchlist import filter_rows_to_watchlist, watchlist_stock_count

# 하위 호환: 발송 허용 유형만 노출
KR_SLACK_ALERT_TYPES: tuple[str, ...] = tuple(sorted(SLACK_SEND_ALLOWED))


def build_kr_stock_alert_slack_text(
    alert_type: str,
    stock: dict[str, Any],
    *,
    reserved_price: str | None = None,
    judgment: str | None = None,
    caution: str | None = None,
) -> str:
    """06_slack_message.md 포맷 (진입 관점·주의 조건 포함)."""
    del judgment, caution
    row = dict(stock)
    row["status"] = alert_type
    if reserved_price:
        row["entry_range"] = reserved_price
    elif stock.get("target_price") and not row.get("entry_range"):
        row["entry_range"] = str(stock.get("target_price"))
    msg = build_slack_message(row)
    if not msg:
        raise ValueError(f"Cannot build slack message for status={alert_type!r}")
    return msg


def build_kr_watchlist_alert_batch(
    rows: list[dict[str, Any]],
    *,
    alert_type: str = "테스트 진입 검토",
    max_count: int = 3,
) -> list[str]:
    """관심종목 풀 내·발송 허용 상태만."""
    if alert_type not in SLACK_SEND_ALLOWED:
        return []
    filtered = filter_rows_to_watchlist(rows)[:max_count]
    out: list[str] = []
    for row in filtered:
        row = {**row, "status": alert_type}
        msg = build_slack_message(row)
        if msg:
            out.append(msg)
    return out


def watchlist_pool_size_line() -> str:
    n = watchlist_stock_count()
    return f"관심 섹터 5개 · 관심종목 {n}개 풀 기준"
