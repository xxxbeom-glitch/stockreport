"""Sequential agent pipeline orchestration (KR: 4-engine flow)."""

from __future__ import annotations

from typing import Any

from .kr_report_pipeline import run_kr_agent_pipeline


def run_agent_pipeline(market_data: dict[str, Any], logger: Any = None) -> dict[str, Any]:
    """Run KR 4-engine pipeline (Report Core → Market Pulse → Risk → Compress).

    Legacy keys (macro, supply, momentum, fundamental, risk, recommendations) are preserved.
    New keys: engines, kr_ui, meta.pipeline.
    """
    return run_kr_agent_pipeline(market_data, logger=logger)
