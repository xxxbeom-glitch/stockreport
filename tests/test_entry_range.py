"""진입 후보 구간 계산·fallback 단위 테스트."""

from __future__ import annotations

import unittest

from agents.kr_intraday_slack.ai_judge import _merge_decision, _resolve_entry_range
from agents.kr_intraday_slack.entry_price import (
    build_entry_range_fallback,
    normalize_ai_entry_range,
)
from agents.kr_intraday_slack.message_tone import compose_sector_stock_block


def _dongjin_candidate() -> dict:
    return {
        "name": "동진쎄미켐",
        "ticker": "005290",
        "sector_name": "반도체 소재",
        "current_price": 61_500,
        "current_price_fmt": "61,500원",
        "day_low": 59_800,
        "prev_close": 60_200,
        "ai_cancel_condition": "57,000원 이탈 또는 거래 급감 시 오늘은 넘기기",
    }


class EntryRangeTest(unittest.TestCase):
    def test_ai_band_70_102_percent(self):
        lo, hi, status = normalize_ai_entry_range(59_500, 61_200, 61_500)
        self.assertEqual(status, "ok")
        self.assertGreaterEqual(lo, int(61_500 * 0.70))
        self.assertLessEqual(hi, 61_500)

    def test_ai_high_capped_to_current(self):
        lo, hi, status = normalize_ai_entry_range(59_000, 62_000, 61_500)
        self.assertLessEqual(hi, 61_500)
        self.assertIn(status, ("ok", "cap_high"))

    def test_ai_too_wide_narrows_to_95_99(self):
        lo, hi, status = normalize_ai_entry_range(50_000, 61_000, 61_500)
        self.assertEqual(status, "too_wide")
        self.assertGreaterEqual(lo, int(61_500 * 0.94))

    def test_fallback_default_when_ai_out_of_band(self):
        cand = _dongjin_candidate()
        item = {"entry_price_range": {"low": 5_000, "high": 6_000}}
        text, lo, hi, source = _resolve_entry_range(cand, item)
        self.assertIn(source, ("rule_anchor", "rule_default"))
        self.assertTrue(text)
        self.assertNotIn("-", text)
        self.assertGreater(lo, 0)
        self.assertGreater(hi, lo)

    def test_dongjin_no_empty_slack_range(self):
        cand = _dongjin_candidate()
        item = {
            "decision": "진입 검토",
            "send_slack": True,
            "entry_price_range": {"low": 6_150, "high": 61_000},
            "reason": "반도체 소재 쪽에서 다시 관심이 붙는 흐름입니다.",
            "entry_view": "눌림 구간 확인.",
            "cancel_condition": "57,000원 이탈 또는 거래 급감 시 오늘은 넘기기",
        }
        merged = _merge_decision(cand, item)
        self.assertTrue(merged.get("ai_send_slack"))
        self.assertNotIn("-", str(merged.get("entry_range") or ""))
        block = compose_sector_stock_block(merged)
        self.assertIsNotNone(block)
        self.assertIn("진입 후보 구간", block or "")
        self.assertNotIn("진입 후보 구간 -", block or "")
        self.assertNotIn("진입 후보 구간 -", block or "")

    def test_unavailable_excludes_send(self):
        cand = {**_dongjin_candidate(), "current_price": 0}
        item = {
            "decision": "진입 검토",
            "send_slack": True,
            "entry_price_range": {"low": 0, "high": 0},
            "reason": "x",
            "entry_view": "y",
            "cancel_condition": "z",
        }
        merged = _merge_decision(cand, item)
        self.assertFalse(merged.get("ai_send_slack"))

    def test_rule_anchor_prefers_day_low(self):
        text, lo, hi, source = build_entry_range_fallback(_dongjin_candidate())
        self.assertEqual(source, "rule_anchor")
        self.assertLessEqual(hi, 61_500)
        self.assertGreaterEqual(lo, int(61_500 * 0.70))


if __name__ == "__main__":
    unittest.main()
