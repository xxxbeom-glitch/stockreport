"""장중 Slack 📡 오늘 새로 볼 종목 메시지 조립 테스트."""

from __future__ import annotations

import unittest

from agents.kr_intraday_slack.message_tone import (
    compose_new_candidate_scan_message,
    compose_new_candidate_stock_block,
    has_new_candidate_scan_shape,
    tier_for_send_row,
)
from agents.kr_intraday_slack.slack_message import build_intraday_slack_thread_bundle


def _sample_row(
    *,
    ticker: str = "222800",
    name: str = "심텍",
    sector: str = "반도체 부품",
    decision: str = "진입 검토",
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "sector_name": sector,
        "ai_decision": decision,
        "status": decision,
        "ai_send_slack": True,
        "current_price_fmt": "124,700원",
        "entry_range": "119,000원 ~ 122,000원",
        "entry_low": 119000,
        "entry_high": 122000,
        "ai_reason": (
            "반도체 부품 쪽에서 거래가 다시 붙는 흐름입니다. "
            "외국인 매수도 같이 들어오고 있습니다."
        ),
        "ai_cancel_condition": "109,000원 이탈 또는 거래 급감 시 오늘은 넘기기",
    }


class TestNewCandidateStockBlock(unittest.TestCase):
    def test_block_shape_and_labels(self):
        block = compose_new_candidate_stock_block(_sample_row())
        self.assertIsNotNone(block)
        assert block is not None
        self.assertIn("• 심텍", block)
        self.assertIn("현재가:", block)
        self.assertIn("볼 구간:", block)
        self.assertIn("이유:", block)
        self.assertIn("주의:", block)
        self.assertNotIn("진입", block)
        self.assertNotIn("추천", block)
        if "매수" in block:
            self.assertIn("외국인 매수", block)
        self.assertNotIn("진입 후보", block)
        self.assertLessEqual(len([ln for ln in block.splitlines() if ln.strip()]), 5)

    def test_tier_green_vs_yellow(self):
        self.assertEqual(tier_for_send_row(_sample_row(decision="진입 검토")), "green")
        self.assertEqual(tier_for_send_row(_sample_row(decision="눌림 확인")), "yellow")

    def test_pass_today_omits_zone(self):
        row = {
            **_sample_row(),
            "ai_send_slack": False,
            "ai_skip_reason": "가격이 많이 올라 부담이 큽니다.",
            "is_chasing": True,
        }
        block = compose_new_candidate_stock_block(row, pass_today=True)
        self.assertIsNotNone(block)
        assert block is not None
        self.assertNotIn("볼 구간:", block)


class TestNewCandidateScanMessage(unittest.TestCase):
    def test_scan_sections(self):
        green = _sample_row()
        yellow = _sample_row(
            ticker="064350", name="켄코아", sector="방산·우주", decision="눌림 확인"
        )
        yellow["current_price_fmt"] = "146,400원"
        yellow["entry_range"] = "139,100원 ~ 144,900원"
        yellow["entry_low"] = 139100
        yellow["entry_high"] = 144900
        text = compose_new_candidate_scan_message(
            slot_clock="14:50",
            send_rows=[green, yellow],
            pass_rows=[],
        )
        self.assertIn("📡 오늘 새로 볼 종목", text)
        self.assertIn("기준: 14:50", text)
        self.assertIn("새 후보: 2개", text)
        self.assertIn("🟢 지금 볼만함", text)
        self.assertIn("🟡 조금 기다림", text)
        self.assertIn("🔴 오늘은 패스", text)
        self.assertIn("심텍", text)
        self.assertIn("켄코아", text)
        self.assertTrue(has_new_candidate_scan_shape(text))

    def test_empty_send_still_has_sections(self):
        text = compose_new_candidate_scan_message(
            slot_clock="10:30", send_rows=[], pass_rows=[]
        )
        self.assertIn("새 후보: 0개", text)
        self.assertIn("_해당 없음_", text)


class TestThreadBundle(unittest.TestCase):
    def test_single_main_no_threads(self):
        row = _sample_row()
        block = compose_new_candidate_stock_block(row)
        assert block
        bundle = build_intraday_slack_thread_bundle(
            [{**row, "slack_stock_block": block}],
            slot="1030",
            allow_empty=False,
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertEqual(bundle["threads"], [])
        self.assertIn("오늘 새로 볼 종목", bundle["main"])

    def test_empty_bundle_with_allow_empty(self):
        bundle = build_intraday_slack_thread_bundle(
            [], slot="1350", allow_empty=True
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertIn("새 후보: 0개", bundle["main"])
        self.assertEqual(bundle["threads"], [])


if __name__ == "__main__":
    unittest.main()
