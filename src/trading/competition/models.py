"""Domain models for AI Trading Competition."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

TeamId = Literal["A", "B", "C", "D"]
DecisionAction = Literal[
    "BUY", "ADD_BUY", "PARTIAL_SELL", "FULL_SELL", "HOLD", "WAIT"
]
OrderType = Literal["MARKET", "LIMIT", "NONE"]
ReviewResult = Literal["APPROVE", "REDUCE", "HOLD", "REJECT"]
AccountStatus = Literal["active", "cash_wait", "investment_suspended"]


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Cannot serialize {type(obj)!r}")


@dataclass
class TeamAccount:
    """Team account — cash, total assets, operational status."""

    team_id: TeamId
    cash_krw: int
    total_assets_krw: int
    status: AccountStatus = "active"
    status_reason: str = ""
    initial_cash_krw: int = 500_000
    started_at: str = field(default_factory=now_kst_iso)
    updated_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TeamAccount:
        return cls(
            team_id=data["team_id"],
            cash_krw=int(data["cash_krw"]),
            total_assets_krw=int(data["total_assets_krw"]),
            status=data.get("status", "active"),
            status_reason=data.get("status_reason", ""),
            initial_cash_krw=int(data.get("initial_cash_krw", 500_000)),
            started_at=data.get("started_at", now_kst_iso()),
            updated_at=data.get("updated_at", now_kst_iso()),
        )


@dataclass
class Position:
    """Single held position for a team."""

    ticker: str
    name: str
    quantity: int
    avg_price_krw: float
    current_price_krw: float = 0.0
    eval_pnl_krw: float = 0.0
    eval_return_pct: float = 0.0
    target_price_krw: Optional[float] = None
    buy_reason_label: str = ""
    buy_reason_detail: str = ""
    review_conditions: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    risk_status: str = "normal"
    opened_at: str = field(default_factory=now_kst_iso)
    updated_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        return cls(
            ticker=data["ticker"],
            name=data.get("name", data["ticker"]),
            quantity=int(data["quantity"]),
            avg_price_krw=float(data["avg_price_krw"]),
            current_price_krw=float(data.get("current_price_krw", 0)),
            eval_pnl_krw=float(data.get("eval_pnl_krw", 0)),
            eval_return_pct=float(data.get("eval_return_pct", 0)),
            target_price_krw=data.get("target_price_krw"),
            buy_reason_label=data.get("buy_reason_label", ""),
            buy_reason_detail=data.get("buy_reason_detail", ""),
            review_conditions=list(data.get("review_conditions") or []),
            evidence_ids=list(data.get("evidence_ids") or []),
            risk_status=data.get("risk_status", "normal"),
            opened_at=data.get("opened_at", now_kst_iso()),
            updated_at=data.get("updated_at", now_kst_iso()),
        )


@dataclass
class TeamPositions:
    """All positions for one team (max 3)."""

    team_id: TeamId
    positions: list[Position] = field(default_factory=list)
    updated_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "positions": [p.to_firestore() for p in self.positions],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TeamPositions:
        return cls(
            team_id=data["team_id"],
            positions=[Position.from_dict(p) for p in data.get("positions") or []],
            updated_at=data.get("updated_at", now_kst_iso()),
        )


@dataclass
class TeamDecision:
    """AI team decision output (spec §8-1)."""

    decision_id: str
    team_id: TeamId
    session_id: str
    action: DecisionAction
    ticker: Optional[str]
    quantity: int
    allocation_krw: int
    order_type: OrderType
    limit_price: Optional[float]
    target_price: Optional[float]
    reason_label: str
    reason_detail: str
    review_conditions: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    created_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass
class PartnerReview:
    """C/D team validator output (spec §8-2)."""

    review_id: str
    decision_id: str
    team_id: TeamId
    result: ReviewResult
    approved_quantity: int
    approved_allocation_krw: int
    reason_label: str
    reason_detail: str
    risk_evidence_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass
class OrderRecord:
    """Order lifecycle record."""

    order_id: str
    decision_id: str
    team_id: TeamId
    ticker: str
    side: Literal["buy", "sell"]
    quantity: int
    order_type: OrderType
    limit_price: Optional[float]
    status: Literal["pending", "partial", "filled", "blocked", "expired", "cancelled"]
    status_reason: str = ""
    session_id: str = ""
    idempotency_key: str = ""
    created_at: str = field(default_factory=now_kst_iso)
    updated_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass
class TradeRecord:
    """Executed trade (spec §12-5)."""

    trade_id: str
    order_id: str
    team_id: TeamId
    ticker: str
    name: str
    side: Literal["buy", "add_buy", "partial_sell", "full_sell"]
    quantity: int
    fill_price_krw: float
    fees_krw: float
    tax_krw: float
    realized_pnl_krw: Optional[float]
    reason_label: str
    reason_detail: str = ""
    executed_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass
class AssetSnapshot:
    """Team asset + benchmark snapshot for chart."""

    snapshot_id: str
    team_id: TeamId
    total_assets_krw: int
    cash_krw: int
    positions_value_krw: int
    kospi_return_pct: Optional[float] = None
    kosdaq_return_pct: Optional[float] = None
    captured_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass
class CompetitionEvent:
    """Shared event analyzer output (spec §7-3)."""

    event_id: str
    event_type: Literal[
        "DISCLOSURE", "NEWS", "PRICE_VOLUME_ANOMALY", "RISK_ALERT"
    ]
    importance: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    direction: Literal["POSITIVE", "NEGATIVE", "MIXED", "UNKNOWN"]
    summary: str
    direct_tickers: list[str] = field(default_factory=list)
    secondary_tickers: list[str] = field(default_factory=list)
    affected_teams: list[TeamId] = field(default_factory=list)
    requires_position_review: bool = False
    evidence_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass
class NotificationRecord:
    """Dashboard / Slack notification."""

    notification_id: str
    category: Literal["trade", "alert", "report", "system"]
    title: str
    sub: str
    team_id: Optional[TeamId] = None
    read: bool = False
    navigate: Optional[str] = None
    created_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass
class AppConfig:
    """App-level config and market state."""

    initialized: bool = False
    initialized_at: str = ""
    operation_started_at: str = ""
    fee_buy_rate: float = 0.0
    fee_sell_rate: float = 0.0
    tax_sell_rate: float = 0.0
    run_mode: str = "live"
    seed_run: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=now_kst_iso)

    def to_firestore(self) -> dict[str, Any]:
        return to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        return cls(
            initialized=bool(data.get("initialized", False)),
            initialized_at=data.get("initialized_at", ""),
            operation_started_at=data.get("operation_started_at", ""),
            fee_buy_rate=float(data.get("fee_buy_rate", 0)),
            fee_sell_rate=float(data.get("fee_sell_rate", 0)),
            tax_sell_rate=float(data.get("tax_sell_rate", 0)),
            run_mode=str(data.get("run_mode", "live")),
            seed_run=dict(data.get("seed_run") or {}),
            updated_at=data.get("updated_at", now_kst_iso()),
        )


__all__ = [
    "TeamAccount",
    "Position",
    "TeamPositions",
    "TeamDecision",
    "PartnerReview",
    "OrderRecord",
    "TradeRecord",
    "AssetSnapshot",
    "CompetitionEvent",
    "NotificationRecord",
    "AppConfig",
    "now_kst_iso",
    "to_dict",
]
