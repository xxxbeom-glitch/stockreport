# -*- coding: utf-8 -*-
"""Phase 3.1 actionable event gate tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.events.gate import apply_actionable_gate
from src.trading.competition.events.models import EvidenceRef, RawSignal
from src.trading.competition.events.scoring import score_signal
from src.trading.competition.events.validator import validate_signal


def _news(title: str, *, scope: str = "eligible_candidate", metrics: dict | None = None) -> RawSignal:
    return RawSignal(
        signal_id=f"news_{hash(title) % 10000}",
        ticker="005930",
        name="삼성전자",
        event_type="NEWS_MATERIAL",
        scope=scope,  # type: ignore[arg-type]
        summary=f"뉴스: {title}",
        evidence=EvidenceRef(
            evidence_id=f"news:{hash(title) % 100000}",
            source_type="naver_news",
            title=title,
        ),
        metrics=metrics or {},
    )


class ActionableGateTest(unittest.TestCase):
    def test_generic_news_rejected_for_eligible(self) -> None:
        signals = [_news("오늘의 증시 브리핑"), _news("장 마감 시황")]
        result = apply_actionable_gate(signals, enrich_market=False)
        self.assertEqual(len(result.passed), 0)
        self.assertEqual(len(result.rejected), 2)

    def test_material_news_with_market_reaction_passes(self) -> None:
        sig = _news("삼성전자, 잠정실적 서프라이즈", metrics={"change_rate_pct": 4.2})
        gs = score_signal(sig)
        self.assertTrue(gs.passes_threshold)
        result = apply_actionable_gate([sig], enrich_market=False)
        self.assertEqual(len(result.passed), 1)

    def test_position_risk_auto_passes(self) -> None:
        sig = RawSignal(
            signal_id="risk1",
            ticker="123456",
            name="보유",
            event_type="POSITION_RISK_ALERT",
            scope="position_holding",
            summary="관리종목",
            evidence=EvidenceRef(
                evidence_id="risk:123456:managed",
                source_type="kis",
            ),
            holding_teams=["B"],
        )
        result = apply_actionable_gate([sig], enrich_market=False)
        self.assertEqual(len(result.passed), 1)
        self.assertTrue(result.passed[0].score.auto_pass)

    def test_missing_evidence_rejected(self) -> None:
        sig = _news("실적 발표")
        sig.evidence.evidence_id = ""
        ok, reason = validate_signal(sig)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_evidence_id")

    def test_per_ticker_news_cap(self) -> None:
        signals = [
            _news("삼성 실적 호조", metrics={"change_rate_pct": 5.0}),
            _news("삼성 수주 계약", metrics={"change_rate_pct": 4.0}),
            _news("삼성 신규 투자", metrics={"change_rate_pct": 3.5}),
        ]
        result = apply_actionable_gate(signals, enrich_market=False)
        news_passed = [p for p in result.passed if p.signal.event_type == "NEWS_MATERIAL"]
        self.assertLessEqual(len(news_passed), 1)

    def test_price_anomaly_passes(self) -> None:
        sig = RawSignal(
            signal_id="pv1",
            ticker="005930",
            name="삼성전자",
            event_type="PRICE_VOLUME_ANOMALY",
            scope="eligible_candidate",
            summary="급등",
            evidence=EvidenceRef(evidence_id="kis:005930:price", source_type="kis"),
            metrics={"change_rate_pct": 6.0},
        )
        result = apply_actionable_gate([sig], enrich_market=False)
        self.assertEqual(len(result.passed), 1)


if __name__ == "__main__":
    unittest.main()
