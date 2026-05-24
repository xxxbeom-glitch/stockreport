"""REPLAY full-audit final report, finalize, Slack."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.trading.competition.constants import INITIAL_CASH_KRW, TEAM_IDS
from src.trading.competition.replay.calendar import resolve_replay_dates
from src.trading.competition.replay.final_report import build_replay_final_report, save_final_report
from src.trading.competition.replay.finalize import mark_accounts_to_market
from src.trading.competition.replay.period import FULL_AUDIT_END, FULL_AUDIT_START, is_full_audit_complete
from src.trading.competition.replay.slack_reports import send_final_report_link


class ReplayFinalizeTests(unittest.TestCase):
    def test_mark_to_market_no_forced_sell(self) -> None:
        accounts = {
            tid: {
                "cash_krw": 100_000,
                "total_assets_krw": INITIAL_CASH_KRW,
                "positions": [
                    {
                        "ticker": "005930",
                        "name": "삼성전자",
                        "quantity": 2,
                        "avg_price_krw": 50_000,
                        "current_price_krw": 50_000,
                    }
                ],
            }
            for tid in TEAM_IDS
        }
        with patch("src.trading.competition.replay.finalize.close_price_krw", return_value=(55_000, None)):
            out, meta = mark_accounts_to_market(accounts, "20260430")
        self.assertFalse(meta.get("forced_liquidation"))
        self.assertEqual(out["A"]["total_assets_krw"], 100_000 + 2 * 55_000)

    def test_full_audit_calendar_fixed(self) -> None:
        with patch("src.trading.competition.replay.calendar.list_trading_dates_result") as mock_list:
            mock_list.return_value = {
                "ok": True,
                "dates": ["20260102", "20260429", "20260430"],
                "primary_source": "kis_daily_chart",
                "errors": [],
            }
            dates = resolve_replay_dates("full_audit", "20241218", "20241220")
        mock_list.assert_called_once_with(FULL_AUDIT_START, FULL_AUDIT_END)
        self.assertEqual(len(dates), 3)

    def test_is_full_audit_complete(self) -> None:
        with patch("src.trading.competition.replay.period.full_audit_last_trading_date", return_value="20260430"):
            self.assertTrue(is_full_audit_complete("20260430"))
            self.assertFalse(is_full_audit_complete("20260115"))


class ReplayFinalReportTests(unittest.TestCase):
    def test_build_and_save_final_report(self) -> None:
        accounts = {tid: {"cash_krw": INITIAL_CASH_KRW, "total_assets_krw": INITIAL_CASH_KRW, "positions": []} for tid in TEAM_IDS}
        report = build_replay_final_report(
            "camp_test",
            [],
            accounts,
            last_trading_date="20260430",
            leakage_summary="PASS",
        )
        self.assertEqual(report["report_type"], "final")
        self.assertEqual(len(report["teams"]), 4)
        self.assertIn("live_readiness", report)
        self.assertIn("benchmark", report)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camp = root / "campaigns" / "camp_test" / "reports"
            camp.mkdir(parents=True)
            with patch("src.trading.competition.replay.final_report.CAMPAIGNS_ROOT", root / "campaigns"):
                with patch("src.trading.competition.replay.final_report.sync_replay_final_report", return_value={"ok": True}):
                    save_final_report("camp_test", report)
            saved = json.loads((camp / "final.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["report_id"], report["report_id"])


class ReplayFinalSlackTests(unittest.TestCase):
    def test_final_slack_message(self) -> None:
        with patch("src.trading.competition.replay.slack_reports._post_slack") as mock_post:
            mock_post.return_value = {"ok": True}
            send_final_report_link(
                {"label": "2026년 1~4월 AI 투자대결 최종 리포트", "url": "http://x/?reportType=final"},
                campaign_id="camp1",
            )
            payload = mock_post.call_args[0][0]
            self.assertIn("리플레이 투자대결이 종료", payload["text"])
            self.assertEqual(payload["blocks"][1]["elements"][0]["text"]["text"], "최종 리포트 확인하기")


if __name__ == "__main__":
    unittest.main()
