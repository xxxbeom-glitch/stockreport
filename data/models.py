"""Shared dataclass models for data modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceStatus:
    """Runtime availability and metadata for an external source."""

    name: str
    enabled: bool
    reason: str = ""


@dataclass(slots=True)
class PriceSnapshot:
    """Simple OHLCV snapshot used by wrappers."""

    symbol: str
    close: float
    prev_close: float
    volume: float
    avg_volume: float

    @property
    def change_pct(self) -> float:
        """Return close-to-close change percentage."""
        if self.prev_close == 0:
            return 0.0
        return ((self.close - self.prev_close) / self.prev_close) * 100.0

    @property
    def volume_ratio(self) -> float:
        """Return current volume versus baseline average."""
        if self.avg_volume == 0:
            return 0.0
        return self.volume / self.avg_volume


@dataclass(slots=True)
class SectorSignal:
    """Sector ETF performance and temperature signal."""

    sector: str
    ticker: str
    ret_5d: float
    vol_ratio: float
    temperature: str
    flow: str


@dataclass(slots=True)
class DiscoveredStock:
    """Candidate stock from dynamic discovery."""

    ticker: str
    name: str
    market: str
    source_tags: list[str] = field(default_factory=list)
    volume_ratio: float | None = None
    foreign_net_buy: float | None = None


@dataclass(slots=True)
class PipelineResult:
    """Top-level data pipeline output."""

    source_status: list[SourceStatus]
    sector_flow: list[SectorSignal]
    discovered_stocks: list[DiscoveredStock]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
