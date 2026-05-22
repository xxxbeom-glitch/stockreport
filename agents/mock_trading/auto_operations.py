# -*- coding: utf-8 -*-
"""
가상투자 자동운영 오케스트레이터 — GitHub Actions·수동 실행 공통.

우선순위:
1. 체결 세션 중/만료 대기 주문 → 지정가 체결·미체결 판정
2. 대기 주문 없음 + 정기 판단 가능(월·목·금 15:30+) → AI 판단·주문 생성
3. 그 외 → 사유 로그·Slack
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.mock_trading.ops_notify import post_mock_trading_ops
from agents.mock_trading.pending_executions_store import (
    list_orders_in_session,
    list_orders_to_expire,
    list_pending,
)
from agents.mock_trading.scheduled_judgment import run_scheduled_judgment
from agents.mock_trading.trading_calendar import (
    is_regular_judgment_day,
    is_trading_day,
    judgment_window_open,
    now_kst,
    regular_entry_type_for_date,
    resolve_regular_entry_type,
)
from agents.mock_trading.virtual_buy_executor import process_limit_orders

KST = ZoneInfo("Asia/Seoul")

_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")


def _fmt_at(at: datetime) -> str:
    at = at.astimezone(KST)
    return at.strftime("%Y-%m-%d %H:%M KST") + f" ({_WEEKDAY_KO[at.weekday()]})"


def _pending_wait_summary(pending: list[dict[str, Any]]) -> str:
    if not pending:
        return ""
    first = min(
        pending,
        key=lambda r: str(r.get("scheduled_at") or r.get("order_created_at") or "z"),
    )
    return (
        f"대기 주문 {len(pending)}건 — 체결 세션 시작 전 "
        f"(다음 시작: {first.get('scheduled_at', '—')}, "
        f"시장: {first.get('order_market', '—')})"
    )


def decide_operation(*, at: datetime | None = None) -> tuple[str, list[str]]:
    at = (at or now_kst()).astimezone(KST)
    reasons: list[str] = []
    pending = list_pending()
    in_session = list_orders_in_session(at)
    to_expire = list_orders_to_expire(at)

    if in_session or to_expire:
        parts = [f"체결·만료 판정 ({len(in_session)}건 세션 중, {len(to_expire)}건 만료 대기)"]
        return "fill_orders", parts

    if pending:
        reasons.append(_pending_wait_summary(pending))
        return "noop", reasons

    if is_regular_judgment_day(at.date()) and judgment_window_open(at):
        entry = resolve_regular_entry_type(at) or ""
        return "scheduled_judgment", [f"정기 AI 판단 ({entry})"]

    if not is_trading_day(at.date()):
        reasons.append("오늘은 주말이라 거래·판단 대상이 아닙니다.")
    elif not is_regular_judgment_day(at.date()):
        w = _WEEKDAY_KO[at.weekday()]
        reasons.append(f"오늘({w})은 정기 AI 판단일이 아닙니다. 판단일: 월·목·금 15:30 이후.")
    elif not judgment_window_open(at):
        entry = regular_entry_type_for_date(at.date())
        if entry:
            reasons.append("정기 판단일이지만 아직 15:30 이전입니다. 장 마감 후 다시 실행하세요.")
        else:
            reasons.append("정기 판단 시간대가 아닙니다 (평일 15:30 이후).")
    else:
        reasons.append("현재 수행할 작업이 없습니다.")

    return "noop", reasons


def run_auto_operations(*, force_judgment: bool = False) -> dict[str, Any]:
    at = now_kst()
    action, action_notes = decide_operation(at=at)

    if force_judgment and action == "noop" and not list_pending():
        if is_regular_judgment_day(at.date()):
            action = "scheduled_judgment"
            action_notes = ["수동 실행 — 정기 판단 강제"]

    payload: dict[str, Any] = {
        "ok": True,
        "at": at.isoformat(timespec="seconds"),
        "at_display": _fmt_at(at),
        "action": action,
        "action_notes": action_notes,
        "pending_count": len(list_pending()),
    }

    if action == "fill_orders":
        fill_result = process_limit_orders(at=at)
        payload["fill"] = fill_result
        filled = sum(
            1 for r in fill_result.get("results") or [] if r.get("status") == "FILLED"
        )
        expired = sum(
            1
            for r in fill_result.get("results") or []
            if r.get("status") == "EXPIRED_UNFILLED"
        )
        slack_lines = [
            f"시각: {_fmt_at(at)}",
            "작업: 대기 주문 체결·만료 확인",
            *action_notes,
            f"처리 {fill_result.get('result_count', 0)}건 — 체결 {filled} / 미체결만료 {expired}",
        ]
        for r in (fill_result.get("results") or [])[:8]:
            slack_lines.append(
                f"· {r.get('ticker')} → {r.get('status')}"
                + (f" @ {r.get('fill_price')}" if r.get("fill_price") else "")
            )
        payload["slack"] = post_mock_trading_ops(slack_lines)

    elif action == "scheduled_judgment":
        judgment = run_scheduled_judgment(at=at)
        payload["judgment"] = judgment
        outcome = judgment.get("outcome") or ""
        orders = judgment.get("orders_placed") or judgment.get("queued_executions") or 0
        slack_lines = [
            f"시각: {_fmt_at(at)}",
            "작업: 정기 AI 판단 · 가상 지정가 주문 생성",
            *action_notes,
            f"결과: {outcome} (주문 {orders}건)",
        ]
        if outcome == "NO_NEW_BUYS":
            slack_lines.append("신규 매수 없음 — 조건 통과 종목 없음")
        payload["slack"] = post_mock_trading_ops(slack_lines)
        if not judgment.get("ok"):
            payload["ok"] = False

    else:
        slack_lines = [
            f"시각: {_fmt_at(at)}",
            "작업: 없음 (대기)",
            *action_notes,
        ]
        payload["slack"] = post_mock_trading_ops(slack_lines)

    return payload
