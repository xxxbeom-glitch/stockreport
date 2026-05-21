"""SendFilter 노출 상한 단위 테스트."""

from __future__ import annotations

import unittest

from agents.kr_intraday_slack.send_filter import (
    select_within_send_limits,
    sort_rows_by_pick_score,
)


def _row(name: str, sector: str, score: float) -> dict:
    return {
        "name": name,
        "ticker": "000001",
        "sector_name": sector,
        "_pick_score": score,
        "ai_send_slack": True,
        "ai_decision": "진입 검토",
        "status": "진입 검토",
    }


class SendFilterLimitsTest(unittest.TestCase):
    def test_two_in_one_sector_within_max_three(self):
        rows = sort_rows_by_pick_score(
            [
                _row("A1", "반도체 부품", 10),
                _row("A2", "반도체 부품", 9),
                _row("B1", "방산·우주", 8),
            ]
        )
        selected, skipped = select_within_send_limits(rows, max_messages=3)
        names = [r["name"] for r in selected]
        self.assertEqual(names, ["A1", "A2", "B1"])
        self.assertEqual(len(skipped), 0)

    def test_sector_cap_two_not_three(self):
        rows = sort_rows_by_pick_score(
            [
                _row("A1", "반도체 부품", 10),
                _row("A2", "반도체 부품", 9),
                _row("A3", "반도체 부품", 8),
            ]
        )
        selected, skipped = select_within_send_limits(rows, max_messages=3)
        self.assertEqual(len(selected), 2)
        self.assertEqual(len(skipped), 1)
        self.assertIn("섹터당 최대", skipped[0]["skip_reason"])

    def test_wrong_order_fixed_by_score_sort(self):
        """점수 정렬 전 [B, A2, A1] 순이어도 A1·A2·B가 선택되어야 함."""
        rows = [
            _row("B1", "방산·우주", 9),
            _row("A2", "반도체 부품", 8),
            _row("A1", "반도체 부품", 10),
        ]
        selected, _ = select_within_send_limits(
            sort_rows_by_pick_score(rows), max_messages=3
        )
        self.assertEqual([r["name"] for r in selected], ["A1", "B1", "A2"])

    def test_three_sectors_one_each(self):
        rows = sort_rows_by_pick_score(
            [
                _row("S1", "반도체 소재", 10),
                _row("P1", "반도체 부품", 9),
                _row("E1", "반도체 장비", 8),
            ]
        )
        selected, skipped = select_within_send_limits(rows, max_messages=3)
        self.assertEqual(len(selected), 3)
        self.assertEqual(len(skipped), 0)


if __name__ == "__main__":
    unittest.main()
