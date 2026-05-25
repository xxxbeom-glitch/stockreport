"""Dashboard REPLAY payload — isolated from LIVE data."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.trading.competition.dashboard.payload import build_dashboard_payload
from src.trading.competition.dashboard.replay_payload import (
    _agent_display_name,
    _build_audit_summary,
    _display_reason,
    _is_executed_trade,
    build_replay_dashboard_payload,
    list_replay_runs,
)

ROOT = Path(__file__).resolve().parents[2]
REPLAY_ROOT = ROOT / "data" / "competition" / "replay"


class ReplayDashboardPayloadTests(unittest.TestCase):
    def test_list_replay_runs_non_empty_when_data_present(self) -> None:
        if not REPLAY_ROOT.is_dir():
            self.skipTest("no replay data")
        runs = list_replay_runs()
        self.assertTrue(runs)
        self.assertIn("replayRunId", runs[0])

    def test_replay_payload_isolated_from_live(self) -> None:
        runs = list_replay_runs()
        if not runs:
            self.skipTest("no replay runs")
        run_id = runs[0]["replayRunId"]
        replay = build_replay_dashboard_payload(run_id)
        live = build_dashboard_payload()

        self.assertEqual(replay["dataSource"], "replay")
        self.assertEqual(live["dataSource"], "live")
        self.assertEqual(replay["replayRunId"], run_id)
        self.assertIn("auditSummary", replay)
        self.assertIn("teamDecisions", replay)
        self.assertNotIn("auditSummary", live)

    def test_replay_costs_warning_visible(self) -> None:
        summary = _build_audit_summary(
            {"cost_model": "costs_not_implemented", "costs_applied": False, "leakage_summary": "PASS"},
            {},
        )
        self.assertEqual(summary["costModel"], "costs_not_implemented")
        self.assertTrue(summary["costsWarning"])
        self.assertFalse(summary["liveReady"])

    def test_executed_trade_filter(self) -> None:
        self.assertFalse(_is_executed_trade({"quantity": 0, "fill_price_krw": 100}))
        self.assertFalse(_is_executed_trade({"quantity": 5, "fill_price_krw": 0}))
        self.assertTrue(
            _is_executed_trade(
                {"quantity": 5, "fill_price_krw": 11430, "trade_id": "tr_x", "executed_at": "2024-12-19"}
            )
        )

    def test_display_reason_strips_mock_detail(self) -> None:
        self.assertEqual(_display_reason("liquidity_watch", "mock provider — no live LLM"), "liquidity_watch")
        self.assertEqual(_agent_display_name("B"), "에이전트 2호")

    def test_replay_payload_agent_names_and_target_price(self) -> None:
        run_dir = REPLAY_ROOT / "replay_20241218_16b6f721"
        if not run_dir.is_dir():
            self.skipTest("smoke run missing")
        payload = build_replay_dashboard_payload("replay_20241218_16b6f721")
        self.assertEqual(payload["agentMeta"]["agent2"]["name"], "에이전트 2호")
        self.assertIsNone(payload["bestAgentKey"])
        self.assertEqual(payload.get("bestAgentTiedCount"), 4)
        self.assertIn("001440", payload["stockCatalog"])
        stock = payload["stockCatalog"]["001440"]
        self.assertEqual(stock.get("targetPrice"), 54000)
        self.assertIn("agent2", stock["agents"])
        trades = payload["tradeHistory"]["agent2"]
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "liquidity_watch")

    def test_replay_manifest_roundtrip(self) -> None:
        for manifest_path in REPLAY_ROOT.glob("*/manifest.json"):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            run_id = manifest["replay_run_id"]
            payload = build_replay_dashboard_payload(run_id)
            self.assertEqual(payload["replayMeta"]["tradingDate"], manifest.get("trading_date"))
            self.assertEqual(payload["auditSummary"]["leakageStatus"], manifest.get("leakage_summary"))
            return
        self.skipTest("no manifest")


if __name__ == "__main__":
    unittest.main()
