"""단타 발송 게이트 — 구간·경고·추격."""

from __future__ import annotations

import unittest

from agents.kr_intraday_slack.entry_price import enrich_intraday_entry, has_valid_warning
from agents.kr_intraday_slack.send_filter import filter_for_slack_send


class IntradayGatesTest(unittest.TestCase):
    def test_enrich_always_has_range_and_warning(self):
        row = enrich_intraday_entry(
            {
                "name": "동진쎄미켐",
                "ticker": "005290",
                "current_price": 61_500,
                "day_low": 59_800,
                "day_high": 65_000,
                "prev_close": 60_200,
            },
            slot="1350",
        )
        self.assertTrue(row.get("entry_range"))
        self.assertTrue(has_valid_warning(row.get("rule_warning_condition")))
        self.assertEqual(row.get("entry_type"), "pullback")

    def test_send_filter_skips_no_warning(self):
        row = {
            "ticker": "005290",
            "name": "동진쎄미켐",
            "sector_name": "반도체 소재",
            "ai_send_slack": True,
            "ai_decision": "진입 검토",
            "entry_range": "59,000원 ~ 61,000원",
            "entry_low": 59000,
            "entry_high": 61000,
            "ai_cancel_condition": "",
            "_pick_score": 5.0,
        }
        to_send, skipped = filter_for_slack_send([row], slot="1350", require_ai=True)
        self.assertEqual(len(to_send), 0)
        self.assertTrue(any("경고" in s.get("skip_reason", "") for s in skipped))


if __name__ == "__main__":
    unittest.main()
