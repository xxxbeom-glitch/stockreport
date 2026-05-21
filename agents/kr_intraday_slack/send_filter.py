"""SendFilterAgent — 최종 슬랙 발송 대상.

노출 규칙 (섹터별 요약 메시지):
- 섹터당 1개 고정이 아니다. 한 섹터에 최대 MAX_STOCKS_PER_SECTOR(2)개까지 상세 카드.
- 전체 상세 종목 수는 max_messages(기본 MAX_MESSAGES_PER_SCAN=3)를 넘지 않는다.
- 조건을 만족한 종목이 많으면 점수(_pick_score) 순으로 채우되, 섹터·전체 상한만 적용.

예 (max_messages=3):
- 반도체 부품 2개 + 방산·우주 1개
- 반도체 소재·부품·장비 각 1개
"""

from __future__ import annotations

from typing import Any

from data.kr_watchlist import watchlist_sector_labels

from .constants import (
    MAX_MESSAGES_PER_SCAN,
    MAX_STOCKS_PER_SECTOR,
    SLACK_SEND_ALLOWED,
    SLACK_SEND_FORBIDDEN,
    normalize_decision,
)
from .entry_price import has_valid_entry_range
from .send_log import entry_range_changed_significantly, last_sent_entry_range, was_sent_today


def _pick_score(row: dict[str, Any]) -> float:
    try:
        return float(row.get("_pick_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def sort_rows_by_pick_score(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """SendFilter·슬랙 요약 전 — 점수 높은 순 (동점은 입력 순서 유지)."""
    return sorted(rows, key=_pick_score, reverse=True)


def sort_send_rows_for_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """섹터 표시 순서(관심 5섹터) → 섹터 내 점수 순."""
    sector_order = {label: i for i, label in enumerate(watchlist_sector_labels())}

    def _key(row: dict[str, Any]) -> tuple[int, float]:
        sector = str(row.get("sector_name") or "").strip() or "기타"
        return (sector_order.get(sector, 99), -_pick_score(row))

    return sorted(rows, key=_key)


def select_within_send_limits(
    rows: list[dict[str, Any]],
    *,
    max_messages: int,
    max_per_sector: int = MAX_STOCKS_PER_SECTOR,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    이미 발송 게이트를 통과한 행만 입력.
    Returns (selected, skipped_due_to_limits).
    """
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    sector_counts: dict[str, int] = {}

    for row in rows:
        sector = str(row.get("sector_name") or "").strip() or "기타"
        base_log = {
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "status": row.get("ai_decision") or row.get("status"),
            "current_price": row.get("current_price_fmt") or row.get("current_price"),
            "entry_range": row.get("entry_range", ""),
            "sent": False,
            "sector_name": sector,
        }

        if len(selected) >= max_messages:
            skipped.append(
                {
                    **base_log,
                    "skip_reason": f"전체 상한 {max_messages}건 초과",
                }
            )
            continue

        if sector_counts.get(sector, 0) >= max_per_sector:
            skipped.append(
                {
                    **base_log,
                    "skip_reason": (
                        f"섹터당 최대 {max_per_sector}종목 초과 ({sector}, "
                        f"전체 상한 {max_messages})"
                    ),
                }
            )
            continue

        selected.append(row)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    return selected, skipped


def filter_for_slack_send(
    evaluated: list[dict[str, Any]],
    *,
    slot: str,
    allow_resend_on_range_change: bool = True,
    require_ai: bool = False,
    max_messages: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (to_send, skipped_log_rows).

    to_send는 max_messages·섹터당 max_per_sector 이내이며,
    점수 순으로 선정된 뒤 슬랙 요약 표시 순으로 정렬된다.
    """
    limit = max_messages if max_messages is not None else MAX_MESSAGES_PER_SCAN
    skipped: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []

    for row in sort_rows_by_pick_score(evaluated):
        status = normalize_decision(
            str(row.get("ai_decision") or row.get("status", ""))
        )
        ticker = str(row.get("ticker", ""))
        name = str(row.get("name", ""))
        base_log = {
            "slot": slot,
            "ticker": ticker,
            "name": name,
            "status": status,
            "current_price": row.get("current_price_fmt") or row.get("current_price"),
            "entry_range": row.get("entry_range", ""),
            "sent": False,
        }

        if require_ai and not row.get("ai_send_slack"):
            skipped.append(
                {
                    **base_log,
                    "skip_reason": row.get("ai_skip_reason") or "AI send_slack=false",
                }
            )
            continue

        if require_ai and not has_valid_entry_range(
            str(row.get("entry_range") or ""),
            entry_low=row.get("entry_low"),
            entry_high=row.get("entry_high"),
        ):
            skipped.append(
                {
                    **base_log,
                    "skip_reason": "진입 후보 구간 없음 — 발송 제외",
                }
            )
            continue

        if status in SLACK_SEND_FORBIDDEN or status not in SLACK_SEND_ALLOWED:
            skipped.append({**base_log, "skip_reason": f"발송 금지 상태: {status}"})
            continue

        if was_sent_today(ticker):
            old_range = last_sent_entry_range(ticker) or ""
            new_range = str(row.get("entry_range") or "")
            if allow_resend_on_range_change and entry_range_changed_significantly(
                old_range, new_range
            ):
                pass
            else:
                skipped.append({**base_log, "skip_reason": "당일 이미 발송됨"})
                continue

        eligible.append({**row, "status": status, "ai_decision": status})

    pool = sort_rows_by_pick_score(eligible)
    selected, limit_skipped = select_within_send_limits(
        pool, max_messages=limit, max_per_sector=MAX_STOCKS_PER_SECTOR
    )
    for item in limit_skipped:
        skipped.append({**item, "slot": slot})

    to_send = sort_send_rows_for_summary(selected)
    return to_send, skipped
