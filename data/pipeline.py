"""End-to-end orchestration for stock report data collection."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

import config
from .models import PipelineResult
from .sector_flow import scan_us_sector_flow
from .sources import get_source_statuses
from .stock_discovery import discover_dynamic_stocks


def run_pipeline() -> PipelineResult:
    """Execute source check, sector scan, and dynamic stock discovery."""
    statuses = get_source_statuses()
    sector_signals = scan_us_sector_flow()
    discovered = discover_dynamic_stocks()

    warnings: list[str] = []
    if not sector_signals:
        warnings.append("No sector signals collected. yfinance might be unavailable.")
    if not discovered:
        warnings.append("No discovered stocks collected. pykrx might be unavailable.")

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "discovery_target_range": [config.DISCOVERY_FINAL_MIN, config.DISCOVERY_FINAL_MAX],
        "retention_days": config.RETENTION_DAYS,
    }
    return PipelineResult(
        source_status=statuses,
        sector_flow=sector_signals,
        discovered_stocks=discovered,
        warnings=warnings,
        metadata=metadata,
    )


def run_pipeline_as_dict() -> dict[str, Any]:
    """Execute pipeline and serialize dataclasses into a dict."""
    result = run_pipeline()
    kr_indices: dict[str, Any] = {}
    us_indices: dict[str, Any] = {}
    indicators: dict[str, Any] = {}

    try:
        from .kr_market import get_kr_indices

        kr_indices = get_kr_indices()
    except Exception as exc:
        result.warnings.append(f"KR index collection failed: {exc}")

    try:
        from .us_market import get_us_indices

        us_indices = get_us_indices()
    except Exception as exc:
        result.warnings.append(f"US index collection failed: {exc}")

    try:
        from .us_market import get_indicators

        indicators = get_indicators()
    except Exception as exc:
        result.warnings.append(f"Market indicator collection failed: {exc}")

    return {
        "source_status": [asdict(item) for item in result.source_status],
        "sector_flow": [asdict(item) for item in result.sector_flow],
        "discovered_stocks": [asdict(item) for item in result.discovered_stocks],
        "indices": {**kr_indices, **us_indices},
        "kr_indices": kr_indices,
        "us_indices": us_indices,
        "market_indicators": indicators,
        "warnings": list(result.warnings),
        "metadata": dict(result.metadata),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_pipeline_as_dict(), ensure_ascii=False, indent=2))
