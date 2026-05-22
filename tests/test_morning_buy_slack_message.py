"""오늘 매수 후보 Slack — 요약+종목별 분리·진입 구간 표시."""

from __future__ import annotations

import unittest

from agents.kr_intraday_slack.entry_price import enrich_intraday_entry
from agents.morning_buy.slack_message import (
    build_morning_buy_slack_bundle,
    build_morning_buy_stock_detail,
)


def _sample_row(
    *,
    name: str,
    ticker: str,
    price: int,
    foreign: float,
    inst: float,
) -> dict:
    row = {
        "name": name,
        "ticker": ticker,
        "current_price": price,
        "current_price_fmt": f"{price:,}원",
        "day_high": int(price * 1.02),
        "volume_ratio_20d": 1.09,
        "trading_value_ratio_20d": 1.17,
        "foreign_net_eok": foreign,
        "inst_net_eok": inst,
        "ai_decision": "진입 검토",
        "ai_reason": "평소보다 거래가 늘고 있어 관심이 들어오는 중임.",
        "ai_cancel_condition": "거래 급감 시 오늘은 넘기기",
    }
    return enrich_intraday_entry(row, slot="1025")


class MorningBuySlackMessageTests(unittest.TestCase):
    def test_two_candidates_produce_three_messages(self) -> None:
        rows = [
            _sample_row(name="하나마이크론", ticker="067310", price=81200, foreign=-17, inst=0),
            _sample_row(name="테스트반도체", ticker="000001", price=45200, foreign=5, inst=3),
        ]
        bundle = build_morning_buy_slack_bundle(
            slot="1025", send_rows=rows, scanned=25
        )
        self.assertEqual(len(bundle["messages"]), 3)
        self.assertIn("후보 2개", bundle["summary"])
        self.assertIn("이어서", bundle["summary"])

    def test_stock_detail_has_required_sections(self) -> None:
        row = _sample_row(
            name="하나마이크론", ticker="067310", price=81200, foreign=-17, inst=0
        )
        text = build_morning_buy_stock_detail(row)
        self.assertIn("현재가:", text)
        self.assertIn("결론:", text)
        self.assertIn("✅ 이 가격이면 사도 됨", text)
        self.assertIn("🚫 이러면 사지 말거나 팔기", text)
        self.assertIn("🔥 오늘 관심도", text)
        self.assertIn("💰 큰손 흐름", text)
        self.assertIn("왜 후보인가?", text)
        self.assertRegex(text, r"\d{1,3}(,\d{3})*\s*~\s*\d{1,3}(,\d{3})*원")
        self.assertIn("외국인", text)

    def test_entry_range_from_enrich_not_empty(self) -> None:
        row = _sample_row(
            name="하나마이크론", ticker="067310", price=81200, foreign=-17, inst=0
        )
        self.assertTrue(str(row.get("entry_range") or "").strip())
        self.assertIsNotNone(row.get("entry_low"))


if __name__ == "__main__":
    unittest.main()
