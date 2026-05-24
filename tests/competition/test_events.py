# -*- coding: utf-8 -*-
"""Phase 3 event detection and analyzer tests."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.events.analyzer import analyze_signal
from src.trading.competition.events.deduplicator import filter_new_signals, is_duplicate_signal
from src.trading.competition.events.models import EvidenceRef, RawSignal
from src.trading.competition.events.router import route_signal
from src.trading.competition.events.pipeline import run_event_scan

MOCK_LEDGER = ROOT / "data" / "mock_trading" / "virtual_positions.json"


def _sig(
    *,
    ticker: str = "005930",
    event_type: str = "DISCLOSURE_POSITIVE",
    scope: str = "eligible_candidate",
    evidence_id: str = "dart:123",
    holding_teams: list[str] | None = None,
    signal_id: str | None = None,
) -> RawSignal:
    return RawSignal(
        signal_id=signal_id or f"sig_{ticker}_{event_type}_{evidence_id}",
        ticker=ticker,
        name="삼성전자",
        event_type=event_type,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        summary="test",
        evidence=EvidenceRef(
            evidence_id=evidence_id,
            source_type="dart",
            title="공급계약",
        ),
        holding_teams=holding_teams or [],
    )


class EventAnalyzerTest(unittest.TestCase):
    def test_analyze_requires_evidence_id(self) -> None:
        bad = _sig(evidence_id="")
        with self.assertRaises(ValueError):
            analyze_signal(bad, use_gemini=False)

    def test_analyzed_event_has_evidence_ids(self) -> None:
        evt = analyze_signal(_sig(), use_gemini=False)
        self.assertTrue(evt.has_evidence())
        self.assertIn("dart:123", evt.evidence_ids)

    def test_analyzer_does_not_create_orders(self) -> None:
        evt = analyze_signal(_sig(), use_gemini=False)
        d = evt.to_dict()
        self.assertNotIn("action", d)
        self.assertNotIn("order_type", d)
        self.assertNotIn("quantity", d)

    def test_position_risk_routes_to_holding_team(self) -> None:
        sig = _sig(
            event_type="POSITION_RISK_ALERT",
            scope="position_holding",
            evidence_id="risk:005930:halt",
            holding_teams=["A", "C"],
        )
        evt = route_signal(sig)
        self.assertEqual(set(evt.affected_teams), {"A", "C"})
        self.assertTrue(evt.requires_position_review)

    def test_disclosure_routes_team_b(self) -> None:
        evt = route_signal(_sig(event_type="DISCLOSURE_POSITIVE"))
        self.assertIn("B", evt.affected_teams)

    def test_price_anomaly_routes_team_a(self) -> None:
        evt = route_signal(_sig(event_type="PRICE_VOLUME_ANOMALY"))
        self.assertIn("A", evt.affected_teams)


class EventDedupTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._events_dir = Path(self._tmpdir) / "events"
        self._events_dir.mkdir()
        self._patches = [
            patch(
                "src.trading.competition.events.store.EVENTS_DIR",
                self._events_dir,
            ),
            patch(
                "src.trading.competition.events.store.DEDUP_INDEX_PATH",
                self._events_dir / "dedup_index.json",
            ),
            patch(
                "src.trading.competition.events.deduplicator.load_dedup_index",
                side_effect=lambda: json.loads(
                    (self._events_dir / "dedup_index.json").read_text(encoding="utf-8")
                )
                if (self._events_dir / "dedup_index.json").is_file()
                else {"keys": {}, "updated_at": ""},
            ),
            patch(
                "src.trading.competition.events.deduplicator.save_dedup_index",
                side_effect=lambda idx: (self._events_dir / "dedup_index.json").write_text(
                    json.dumps(idx, ensure_ascii=False), encoding="utf-8"
                ),
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_duplicate_signal_blocked(self) -> None:
        s1 = _sig()
        s2 = _sig()
        new, dup = filter_new_signals([s1, s2])
        self.assertEqual(len(new), 1)
        self.assertEqual(len(dup), 1)
        self.assertTrue(is_duplicate_signal(s2))


class EventPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._events_dir = Path(self._tmpdir) / "events"
        self._events_dir.mkdir()
        self._ledger_mtime = (
            MOCK_LEDGER.stat().st_mtime if MOCK_LEDGER.is_file() else None
        )

        def _fake_scanner(ticker, name, **kwargs):
            scope = kwargs.get("scope", "eligible_candidate")
            teams = kwargs.get("holding_teams") or []
            if scope == "position_holding":
                return [
                    RawSignal(
                        signal_id=f"sig_{ticker}_risk",
                        ticker=ticker,
                        name=name or "보유종목",
                        event_type="POSITION_RISK_ALERT",
                        scope="position_holding",
                        summary="test",
                        evidence=EvidenceRef(
                            evidence_id=f"risk:{ticker}:managed",
                            source_type="kis",
                        ),
                        holding_teams=teams,
                    )
                ]
            return [
                RawSignal(
                    signal_id=f"sig_{ticker}_pv",
                    ticker=ticker,
                    name=name or "삼성전자",
                    event_type="PRICE_VOLUME_ANOMALY",
                    scope="eligible_candidate",
                    summary="test",
                    evidence=EvidenceRef(
                        evidence_id=f"price:{ticker}",
                        source_type="kis",
                    ),
                    metrics={"change_rate_pct": 6.0},
                )
            ]

        self._fake_scanner = _fake_scanner

        self._patches = [
            patch(
                "src.trading.competition.events.store.EVENTS_DIR",
                self._events_dir,
            ),
            patch(
                "src.trading.competition.events.store.RAW_SIGNALS_PATH",
                self._events_dir / "raw_signals.jsonl",
            ),
            patch(
                "src.trading.competition.events.store.ACTIONABLE_EVENTS_PATH",
                self._events_dir / "actionable_events.jsonl",
            ),
            patch(
                "src.trading.competition.events.store.ANALYZED_EVENTS_PATH",
                self._events_dir / "analyzed_events.jsonl",
            ),
            patch(
                "src.trading.competition.events.store.DEDUP_INDEX_PATH",
                self._events_dir / "dedup_index.json",
            ),
            patch(
                "src.trading.competition.events.store.SCAN_SUMMARY_PATH",
                self._events_dir / "scan_summary.json",
            ),
            patch(
                "src.trading.competition.events.store.GATE_REJECTED_PATH",
                self._events_dir / "gate_rejected.jsonl",
            ),
            patch(
                "src.trading.competition.events.pipeline.build_position_watch_map",
                return_value={
                    "123456": {"name": "보유종목", "holding_teams": ["B"]},
                },
            ),
            patch(
                "src.trading.competition.events.pipeline.build_eligible_map",
                return_value={
                    "005930": {"ticker": "005930", "name": "삼성전자"},
                },
            ),
            patch(
                "src.trading.competition.events.store.firestore_client",
                return_value=(None, {"ok": False}),
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        if self._ledger_mtime is not None and MOCK_LEDGER.is_file():
            self.assertEqual(MOCK_LEDGER.stat().st_mtime, self._ledger_mtime)

    def test_pipeline_scans_positions_and_eligible(self) -> None:
        result = run_event_scan(ticker_scanner=self._fake_scanner)
        self.assertTrue(result["ok"])
        summary = result["summary"]
        self.assertEqual(summary["position_tickers_scanned"], 1)
        self.assertEqual(summary["eligible_tickers_scanned"], 1)
        self.assertGreaterEqual(summary["signals_new"], 2)
        self.assertGreaterEqual(summary["gate_passed"], 1)
        self.assertGreaterEqual(summary["actionable_events"], 1)
        self.assertGreaterEqual(summary["events_requiring_position_review"], 1)

    def test_position_signal_not_limited_by_eligible(self) -> None:
        """Held ticker 123456 is not in eligible map but still scanned."""
        with patch(
            "src.trading.competition.events.pipeline.build_eligible_map",
            return_value={},
        ):
            result = run_event_scan(ticker_scanner=self._fake_scanner, scan_eligible=False)
        self.assertEqual(result["summary"]["position_tickers_scanned"], 1)
        types = result["summary"].get("by_event_type_raw", {})
        self.assertIn("POSITION_RISK_ALERT", types)


if __name__ == "__main__":
    unittest.main()
