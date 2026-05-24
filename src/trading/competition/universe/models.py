"""Universe symbol metadata for competition entry filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Market = Literal["KOSPI", "KOSDAQ", "UNKNOWN"]
SecurityType = Literal["common", "preferred", "etf", "etn", "spac", "reit", "unknown"]
RiskStatus = Literal["normal", "managed", "halt", "liquidation", "warning", "risk"]


@dataclass
class SymbolSnapshot:
    """Minimal symbol data for common entry filter (spec §2-2)."""

    ticker: str
    name: str
    market: Market = "UNKNOWN"
    security_type: SecurityType = "common"
    current_price_krw: Optional[int] = None
    avg_trading_value_20d_krw: Optional[int] = None
    risk_status: RiskStatus = "normal"
    risk_exclude_new_entry: bool = False
    risk_notes: list[str] = field(default_factory=list)
    tradable: bool = True
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ticker_normalized(self) -> str:
        return str(self.ticker).zfill(6)
