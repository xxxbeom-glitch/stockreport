# -*- coding: utf-8 -*-
"""Phase 2 universe builder tests."""

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

from src.trading.competition.universe.builder import (
    build_universe,
    evaluate_entry_eligibility,
    load_eligible_universe,
)
from src.trading.competition.universe.security_type import classify_security_type

MOCK_TRADING_LEDGER = ROOT / "data" / "mock_trading" / "virtual_positions.json"


def _stock(
    ticker: str,
    name: str,
    *,
    market: str = "KOSPI",
    price: int = 50_000,
    avg_tv: int = 5_000_000_000,
    risk_verified: bool = True,
    risk_status: str = "normal",
    risk_exclude: bool = False,
) -> dict:
    rec = {
        "ticker": ticker,
        "name": name,
        "market": market,
        "current_price_krw": price,
        "avg_trading_value_20d_krw": avg_tv,
        "history_days_present": 20,
        "data_sources": ["pykrx"],
    }
    if risk_verified:
        rec.update(
            {
                "risk_check_status": "verified",
                "risk_status": risk_status,
                "risk_exclude_new_entry": risk_exclude,
                "risk_notes": [],
                "tradable": True,
            }
        )
    else:
        rec.update(
            {
                "risk_check_status": "unverified",
                "risk_status": "unknown",
                "risk_exclude_new_entry": False,
                "risk_notes": [],
            }
        )
    return rec


def _mock_collector(_date: str) -> tuple[list[dict], list[str]]:
    stocks = [
        _stock("005930", "삼성전자"),
        _stock("111111", "KODEX 200 ETF", price=30_000),
        _stock("222222", "삼성전자우", price=40_000),
        _stock("333333", "고가주", price=150_000),
        _stock("444444", "저유동", avg_tv=1_000_000_000),
        _stock("555555", "관리종목", risk_status="managed", risk_exclude=True),
        {
            "ticker": "666666",
            "name": "데이터없음",
            "market": "KOSDAQ",
            "current_price_krw": None,
            "avg_trading_value_20d_krw": None,
            "history_days_present": 2,
            "data_sources": ["pykrx"],
            "risk_check_status": "verified",
            "risk_status": "normal",
            "risk_exclude_new_entry": False,
            "risk_notes": [],
            "tradable": True,
        },
        _stock("777777", "위험미확인", risk_verified=False),
    ]
    return stocks, []


def _kis_ok(ticker: str) -> dict | None:
    if ticker == "777777":
        return None
    if ticker == "555555":
        return {"raw": {"mang_issu_cls_code": "Y"}, "price": 50_000}
    return {"raw": {}, "price": 50_000}


class UniverseBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._out = Path(self._tmpdir) / "universe"
        self._ledger_mtime_before = (
            MOCK_TRADING_LEDGER.stat().st_mtime if MOCK_TRADING_LEDGER.is_file() else None
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        if self._ledger_mtime_before is not None and MOCK_TRADING_LEDGER.is_file():
            self.assertEqual(
                MOCK_TRADING_LEDGER.stat().st_mtime,
                self._ledger_mtime_before,
                "mock_trading ledger was modified",
            )

    def test_eligible_common_passes(self) -> None:
        ok, reason, cat = evaluate_entry_eligibility(_stock("005930", "삼성전자"))
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertEqual(cat, "eligible")

    def test_price_over_100k_excluded(self) -> None:
        ok, reason, cat = evaluate_entry_eligibility(
            _stock("333333", "고가주", price=150_000)
        )
        self.assertFalse(ok)
        self.assertIn("price_over", reason)
        self.assertEqual(cat, "price_over_limit")

    def test_low_liquidity_excluded(self) -> None:
        ok, reason, cat = evaluate_entry_eligibility(
            _stock("444444", "저유동", avg_tv=1_000_000_000)
        )
        self.assertFalse(ok)
        self.assertIn("avg_tv_below", reason)
        self.assertEqual(cat, "low_liquidity")

    def test_etf_excluded(self) -> None:
        self.assertEqual(classify_security_type("KODEX 200 ETF"), "etf")
        ok, reason, cat = evaluate_entry_eligibility(
            _stock("111111", "KODEX 200 ETF")
        )
        self.assertFalse(ok)
        self.assertIn("excluded_security_type", reason)

    def test_preferred_excluded(self) -> None:
        ok, reason, _ = evaluate_entry_eligibility(_stock("222222", "삼성전자우"))
        self.assertFalse(ok)
        self.assertIn("preferred", reason)

    def test_risk_excluded(self) -> None:
        ok, reason, cat = evaluate_entry_eligibility(
            _stock("555555", "관리종목", risk_status="managed", risk_exclude=True)
        )
        self.assertFalse(ok)
        self.assertIn("risk:", reason)
        self.assertEqual(cat, "risk")

    def test_missing_data_excluded(self) -> None:
        rec = {
            "ticker": "666666",
            "name": "데이터없음",
            "market": "KOSDAQ",
            "current_price_krw": None,
            "avg_trading_value_20d_krw": None,
            "history_days_present": 2,
            "risk_check_status": "verified",
            "risk_status": "normal",
            "risk_exclude_new_entry": False,
        }
        ok, reason, cat = evaluate_entry_eligibility(rec)
        self.assertFalse(ok)
        self.assertIn("data_unavailable", reason)
        self.assertEqual(cat, "data_unavailable")

    def test_risk_unverified_excluded(self) -> None:
        ok, reason, cat = evaluate_entry_eligibility(
            _stock("777777", "위험미확인", risk_verified=False)
        )
        self.assertFalse(ok)
        self.assertIn("risk_unverified", reason)

    def test_build_writes_all_output_files(self) -> None:
        result = build_universe(
            "20260523",
            pykrx_collector=_mock_collector,
            kis_fetcher=_kis_ok,
            output_dir=self._out,
        )
        self.assertTrue(result["ok"])
        for key in ("all_stocks", "eligible", "excluded", "summary"):
            self.assertTrue(Path(result["paths"][key]).is_file())

        eligible = json.loads(
            (self._out / "eligible_entry_universe.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(eligible["stocks"]), 1)
        self.assertEqual(eligible["stocks"][0]["ticker"], "005930")

        summary = json.loads((self._out / "build_summary.json").read_text())
        self.assertEqual(summary["total_collected"], 8)
        self.assertEqual(summary["eligible_count"], 1)
        self.assertIn("filter_exclusion_counts", summary)

    @patch("src.trading.competition.universe.builder.now_kst_iso")
    def test_rebuild_updates_generated_at(self, mock_now) -> None:
        mock_now.side_effect = ["2026-05-24T10:00:00+09:00", "2026-05-24T11:00:00+09:00"]
        build_universe(
            "20260523",
            pykrx_collector=_mock_collector,
            kis_fetcher=_kis_ok,
            output_dir=self._out,
        )
        first = json.loads(
            (self._out / "build_summary.json").read_text(encoding="utf-8")
        )["generated_at"]

        build_universe(
            "20260524",
            pykrx_collector=_mock_collector,
            kis_fetcher=_kis_ok,
            output_dir=self._out,
        )
        second = json.loads(
            (self._out / "build_summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(second["trading_date"], "20260524")
        self.assertNotEqual(second["generated_at"], first)

    def test_load_eligible_universe(self) -> None:
        build_universe(
            "20260523",
            pykrx_collector=_mock_collector,
            kis_fetcher=_kis_ok,
            output_dir=self._out,
        )
        loaded = load_eligible_universe(self._out / "eligible_entry_universe.json")
        self.assertEqual(len(loaded), 1)


if __name__ == "__main__":
    unittest.main()
