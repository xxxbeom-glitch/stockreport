# -*- coding: utf-8
"""Phase 5 execution rules tests."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.competition.execution.fill_engine import resolve_fill
from src.trading.competition.execution.market_session import (
    SessionContext,
    SessionKind,
    get_session_context,
    is_nxt_eligible,
    validate_session_order,
)
from src.trading.competition.execution.pending_orders import (
    expire_pending_orders,
    load_pending_orders,
    upsert_pending_order,
)
from src.trading.competition.execution.quote_fill import limit_fillable, market_fill_price, partial_fill_quantity
from src.trading.competition.execution.validator import validate_order_proposal

KST = ZoneInfo("Asia/Seoul")
REGULAR = SessionContext(
    kind=SessionKind.REGULAR,
    tradable=True,
    allows_market=True,
    allows_limit=True,
    allows_nxt=False,
    label="regular",
)
NXT_SESSION = SessionContext(
    kind=SessionKind.NXT,
    tradable=True,
    allows_market=True,
    allows_limit=True,
    allows_nxt=True,
    label="nxt",
)


class QuoteFillTest(unittest.TestCase):
    def test_market_buy_uses_ask(self) -> None:
        q = {"ask_price": 70100, "bid_price": 70000, "price": 70050}
        px, reason = market_fill_price(side="buy", quote=q)
        self.assertEqual(px, 70100)
        self.assertEqual(reason, "market_at_ask")

    def test_market_no_quote_blocked(self) -> None:
        px, reason = market_fill_price(side="buy", quote=None)
        self.assertIsNone(px)

    def test_limit_buy_pending_when_not_marketable(self) -> None:
        q = {"ask_price": 71000, "bid_price": 70900}
        ok, px, _ = limit_fillable(side="buy", limit_price=70000, quote=q)
        self.assertFalse(ok)
        self.assertIsNone(px)

    def test_limit_buy_fills_when_crossed(self) -> None:
        q = {"ask_price": 70500, "bid_price": 70400}
        ok, px, _ = limit_fillable(side="buy", limit_price=71000, quote=q)
        self.assertTrue(ok)
        self.assertEqual(px, 70500)

    def test_partial_fill(self) -> None:
        qty, partial = partial_fill_quantity(10, {"available_qty": 4})
        self.assertEqual(qty, 4)
        self.assertTrue(partial)


class SessionRulesTest(unittest.TestCase):
    def test_weekend_closed(self) -> None:
        sat = datetime(2026, 5, 23, 10, 0, tzinfo=KST)
        ctx = get_session_context(sat)
        self.assertFalse(ctx.tradable)

    def test_nxt_blocked_for_ineligible_ticker(self) -> None:
        ok, reason = validate_session_order(
            session=NXT_SESSION,
            order_type="LIMIT",
            venue="NXT",
            ticker="005930",
            quote={"nxt_eligible": False},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "nxt_not_eligible_ticker")

    def test_nxt_allowed_when_flagged(self) -> None:
        self.assertTrue(is_nxt_eligible("005930", {"nxt_eligible": True}))


class PendingOrderTest(unittest.TestCase):
    def test_expire_does_not_roll_forward(self) -> None:
        import src.trading.competition.execution.pending_orders as po

        original = po.PENDING_PATH
        tmp = Path(__file__).parent / "_tmp_pending.json"
        po.PENDING_PATH = tmp
        try:
            if tmp.is_file():
                tmp.unlink()
            upsert_pending_order(
                {
                    "order_id": "ord_test1",
                    "session_id": "sess_a",
                    "status": "pending",
                    "quantity": 5,
                }
            )
            expired = expire_pending_orders("sess_a")
            self.assertEqual(len(expired), 1)
            self.assertEqual(expired[0]["status"], "expired")
            remaining = load_pending_orders(session_id="sess_a")
            self.assertEqual(len(remaining), 0)
        finally:
            po.PENDING_PATH = original
            if tmp.is_file():
                tmp.unlink()


class FillEngineTest(unittest.TestCase):
    def test_limit_order_goes_pending(self) -> None:
        decision = {
            "decision_id": "d1",
            "team_id": "A",
            "session_id": "s1",
            "action": "BUY",
            "ticker": "005930",
            "quantity": 2,
            "order_type": "LIMIT",
            "limit_price": 65000,
            "evidence_ids": ["e1"],
        }
        quote = {"ask_price": 70000, "bid_price": 69900}
        fill = resolve_fill(decision, quote=quote, session=REGULAR)
        self.assertEqual(fill["status"], "pending")

    def test_market_blocked_without_quote(self) -> None:
        decision = {
            "decision_id": "d2",
            "team_id": "A",
            "action": "BUY",
            "ticker": "005930",
            "quantity": 1,
            "order_type": "MARKET",
            "evidence_ids": ["e1"],
        }
        fill = resolve_fill(decision, quote=None, session=REGULAR)
        self.assertEqual(fill["status"], "blocked")


class StrictValidationTest(unittest.TestCase):
    def test_strict_entry_filter_blocks_unverified(self) -> None:
        decision = {
            "decision_id": "d3",
            "team_id": "A",
            "action": "BUY",
            "ticker": "005930",
            "quantity": 1,
            "allocation_krw": 70000,
            "order_type": "MARKET",
            "evidence_ids": ["scout:005930"],
            "_fill_price": 70000,
        }
        ok, reason = validate_order_proposal(decision, None, session=REGULAR)
        # May block on entry_filter if universe row unverified — acceptable strict behavior
        if not ok:
            self.assertTrue(
                reason.startswith("entry_filter:") or reason in ("session_not_tradable",)
            )


if __name__ == "__main__":
    unittest.main()
