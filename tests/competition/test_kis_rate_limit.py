# -*- coding: utf-8 -*-
"""KIS REST rate limiting and EGW00201 handling."""

from __future__ import annotations

import logging
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from data import kis_client as kc
from data import kis_rate_limit as krl


class KISRateLimiterTests(unittest.TestCase):
    def setUp(self) -> None:
        krl.reset_kis_rate_limit_state()
        kc.reset_kis_auth_state(clear_token=True)
        if kc._default_client is not None:
            kc._default_client._token_issue_calls = 0
            kc._default_client._memory_token = "tok_test"
            kc._default_client._memory_issued_at = kc._now()

    def test_parallel_acquire_respects_configured_rps(self) -> None:
        with patch.dict("os.environ", {"KIS_MAX_REQUESTS_PER_SECOND": "10"}, clear=False):
            krl.reset_kis_rate_limit_state()
            stamps: list[float] = []
            lock = threading.Lock()

            def _worker() -> None:
                for _ in range(3):
                    krl.kis_rate_limiter_acquire()
                    with lock:
                        stamps.append(time.monotonic())

            threads = [threading.Thread(target=_worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            stamps.sort()
            min_interval = krl.rate_limiter_min_interval()
            for prev, cur in zip(stamps, stamps[1:]):
                self.assertGreaterEqual(cur - prev, min_interval * 0.85)

    def test_egw00201_limited_retries_then_halt(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "KIS_MAX_REQUESTS_PER_SECOND": "100",
                "KIS_RATE_LIMIT_MAX_RETRIES": "2",
                "KIS_RATE_LIMIT_HALT_AFTER": "3",
            },
            clear=False,
        ):
            krl.reset_kis_rate_limit_state()
            client = kc.KISClient()
            client._memory_token = "tok"
            client._memory_issued_at = kc._now()

            rate_body = {
                "rt_cd": "1",
                "msg_cd": "EGW00201",
                "msg1": "초당 거래건수를 초과하였습니다.",
            }
            res = MagicMock(status_code=200, text="{}")
            res.json.return_value = rate_body
            res.raise_for_status = MagicMock()

            http_calls: list[int] = []

            def _fake_get(*args, **kwargs) -> MagicMock:
                http_calls.append(1)
                return res

            with patch("data.kis_client.requests.get", side_effect=_fake_get):
                out1 = client._get(
                    "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                    "FHKST03010100",
                    {"FID_INPUT_ISCD": "005930"},
                )
                out2 = client._get(
                    "/uapi/domestic-stock/v1/quotations/inquire-price",
                    "FHKST01010100",
                    {"FID_INPUT_ISCD": "000660"},
                )
                out3 = client._get(
                    "/uapi/domestic-stock/v1/quotations/inquire-price",
                    "FHKST01010100",
                    {"FID_INPUT_ISCD": "035420"},
                )

            self.assertIsNone(out1)
            self.assertIsNone(out2)
            self.assertIsNone(out3)
            summary = krl.kis_rate_limit_observability()
            self.assertTrue(summary["halted"])
            self.assertGreaterEqual(summary["rate_limit_error_count"], 3)
            self.assertIn("FHKST03010100", summary["affected_tr_ids"])
            self.assertGreaterEqual(summary["retry_count"], 1)
            # Halt stops further HTTP; only first tr_id may appear before threshold.
            self.assertLessEqual(len(http_calls), 9)

    def test_rate_limit_logs_first_and_summary_only(self) -> None:
        krl.reset_kis_rate_limit_state()
        with patch.dict("os.environ", {"KIS_RATE_LIMIT_HALT_AFTER": "5"}, clear=False):
            krl.reset_kis_rate_limit_state()
            with self.assertLogs("data.kis_rate_limit", level="WARNING") as captured:
                for i in range(8):
                    krl.record_kis_rate_limit_error(
                        tr_id="FHKST01010100" if i % 2 == 0 else "FHKST03010100",
                        msg1="초당 거래건수를 초과하였습니다.",
                        retried=i > 0,
                    )
        joined = "\n".join(captured.output)
        self.assertIn("EGW00201", joined)
        self.assertIn("halt activated", joined)
        self.assertEqual(joined.count("EGW00201"), 1)
        self.assertEqual(joined.count("halt activated"), 1)

    def test_halt_blocks_further_get_without_http(self) -> None:
        krl.reset_kis_rate_limit_state()
        krl._rate_limit_state.halted = True
        client = kc.KISClient()
        client._memory_token = "tok"
        client._memory_issued_at = kc._now()
        with patch("data.kis_client.requests.get") as mock_get:
            out = client._get("/path", "FHKST01010100", {})
        mock_get.assert_not_called()
        self.assertIsNone(out)


class KISRateLimitRunnerTests(unittest.TestCase):
    def test_runner_returns_rate_limit_exceeded_without_traceback(self) -> None:
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock

        from src.trading.competition.replay.runner import run_replay_single_day

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "replay"
            root.mkdir(parents=True)
            with mock.patch(
                "src.trading.competition.replay.observability.replay_run_dir",
                side_effect=lambda rid: root / rid,
            ):
                with mock.patch(
                    "src.trading.competition.replay.observability.providers_configuration",
                    return_value={"kis_configured": True, "pykrx_available": True},
                ):
                    with mock.patch(
                        "data.kis_client.preflight_kis_auth",
                        return_value={"ok": True, "token_issue_calls": 1},
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.runner.build_close_snapshot",
                            return_value={"ok": True, "trading_date": "20260109"},
                        ):
                            with mock.patch(
                                "data.kis_client.is_kis_rate_limit_halted",
                                return_value=True,
                            ):
                                with mock.patch(
                                    "data.kis_client.kis_rate_limit_summary",
                                    return_value={
                                        "halted": True,
                                        "rate_limit_error_count": 10,
                                        "retry_count": 4,
                                        "affected_tr_ids": ["FHKST01010100", "FHKST03010100"],
                                        "configured_rps": 8.0,
                                        "last_msg_cd": "EGW00201",
                                    },
                                ):
                                    result = run_replay_single_day("20260109", sync_firestore=False)

            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "kis_rate_limit_exceeded")
            run_dir = next(root.iterdir())
            meta = json.loads((run_dir / "observability" / "execution_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "kis_rate_limit_exceeded")
            self.assertEqual(meta["kis_rate_limit"]["rate_limit_error_count"], 10)
            self.assertEqual(meta["kis_rate_limit"]["configured_rps"], 8.0)
            events = (run_dir / "observability" / "pipeline_events.jsonl").read_text(encoding="utf-8")
            self.assertIn("kis_rate_limit", events)
            self.assertIn("FHKST01010100", events)


if __name__ == "__main__":
    unittest.main()
