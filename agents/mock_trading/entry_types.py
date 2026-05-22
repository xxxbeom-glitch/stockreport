# -*- coding: utf-8 -*-
"""정기·긴급 가상매수 entry / trigger / execution 상수."""

from __future__ import annotations

from typing import Literal

EntryType = Literal[
    "REGULAR_MON",
    "REGULAR_THU",
    "REGULAR_FRI_WEEKEND",
    "INTRADAY_ALERT",
]

TriggerType = Literal["REGULAR", "INTRADAY"]

ExecutionMarket = Literal["NXT_AFTER_MARKET", "KRX_REGULAR"]

REGULAR_ENTRY_TYPES: tuple[str, ...] = (
    "REGULAR_MON",
    "REGULAR_THU",
    "REGULAR_FRI_WEEKEND",
)

ENTRY_TYPE_BY_WEEKDAY: dict[int, str] = {
    0: "REGULAR_MON",  # Monday
    3: "REGULAR_THU",
    4: "REGULAR_FRI_WEEKEND",
}

POSITION_STATUS_HOLDING = "HOLDING"

DEFAULT_MARKET_LABEL = "한국시장"

# NXT 애프터마켓: 체결 확인 15:40~20:00, 20:00 미체결 만료, 20:05 최종 만료 배치
EXECUTION_SLOT_NXT_START = (15, 40)
EXECUTION_SLOT_NXT_END = (20, 0)
EXECUTION_SLOT_NXT_FINAL_EXPIRE = (20, 5)
# 하위 호환 alias
EXECUTION_SLOT_NXT = EXECUTION_SLOT_NXT_START

EXECUTION_SLOT_KRX_OPEN = (9, 10)
EXECUTION_SLOT_KRX_END = (15, 30)
JUDGMENT_AFTER_CLOSE = (15, 30)

# 가상 지정가 주문 상태 (pending_executions.json)
ORDER_STATUS_PENDING = "ORDER_PENDING"
ORDER_STATUS_FILLED = "FILLED"
ORDER_STATUS_EXPIRED = "EXPIRED_UNFILLED"
# 레거시
LEGACY_STATUS_PENDING = "PENDING"
