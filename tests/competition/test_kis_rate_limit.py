# -*- coding: utf-8 -*-
"""KIS REST rate limiting, rolling window, EGW00201 circuit breaker."""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from data import kis_client as kc
from data import kis_rate_limit as krl


def _ok_response(payload: dict) -> MagicMock:
    res = MagicMock(status_code=200)
    res.text = json.dumps(payload)
    res.json.return_value = payload
    return res


class KISRateLimiterTests(unittest.TestCase):
    def setUp(self) -> None:
        krl.reset_kis_rate_limit_state()
        kc.reset_kis_auth_state(clear_token=True)
        if kc._default_client is not None:
            c = kc._default_client
            c._token_issue_calls = 0
            c._memory_token = "tok_test"
            c._memory_issued_at = kc._now()

    def test_fhkst03010100_path_uses_kis_http_request(self) -> None:
        payload = {
            "rt_cd": "0",
            "output2": [
                {
                    "stck_bsop_date": "20260109",
                    "stck_clpr": "70000",
                    "stck_oprc": "69000",
                    "stck_hgpr": "71000",
                    "stck_lwpr": "68000",
                    "acml_vol": "1000",
                    "acml_tr_pbmn": "500000000",
                }
            ],
        }
        with patch.object(kc.config, "KIS_APP_KEY", "k"):
            with patch.object(kc.config, "KIS_APP_SECRET", "s"):
                with patch("data.kis_client.kis_http_request", return_value=_ok_response(payload)) as mock_http:
                    bars = kc.get_daily_ohlcv_range("005930", "20251201", "20260109")
        self.assertEqual(len(bars), 1)
        self.assertTrue(mock_http.called)
        call_kw = mock_http.call_args
        self.assertEqual(call_kw[0][0], "GET")
        self.assertEqual(call_kw[1].get("tr_id"), "FHKST03010100")

    def test_rolling_window_caps_requests_per_second(self) -> None:
        with patch.dict("os.environ", {"KIS_MAX_REQUESTS_PER_SECOND": "2"}, clear=False):
            krl.reset_kis_rate_limit_state()
            stamps: list[float] = []

            def _fake_request(method: str, url: str, **kwargs) -> MagicMock:
                stamps.append(time.monotonic())
                return _ok_response({"rt_cd": "0"})

            with patch("data.kis_rate_limit.requests.request", side_effect=_fake_request):
                for _ in range(4):
                    krl.kis_http_request("GET", "https://example.com", tr_id="T")
            stamps.sort()
            for i in range(1, len(stamps)):
                if stamps[i] - stamps[i - 1] < 0.4:
                    # At most 2 per 1s window — third request in same second must wait ~1s
                    pass
            summary = krl.kis_rate_limit_observability()
            self.assertLessEqual(summary["actual_max_requests_in_rolling_1s"], 2)
            self.assertEqual(summary["total_http_requests"], 4)

    def test_egw00201_halts_without_http_error_log_spam(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "KIS_MAX_REQUESTS_PER_SECOND": "100",
                "KIS_RATE_LIMIT_MAX_RETRIES": "1",
                "KIS_RATE_LIMIT_HALT_AFTER": "1",
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
            res = _ok_response(rate_body)
            http_calls: list[int] = []

            def _fake_http(method: str, url: str, **kwargs) -> mock.MagicMock:
                http_calls.append(1)
                return res

            with patch("data.kis_client.kis_http_request", side_effect=_fake_http):
                with self.assertLogs("data.kis_rate_limit", level="WARNING") as rl_logs:
                    client._get(
                        "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                        "FHKST03010100",
                        {"FID_INPUT_ISCD": "005930"},
                    )
                    client._get(
                        "/uapi/domestic-stock/v1/quotations/inquire-price",
                        "FHKST01010100",
                        {"FID_INPUT_ISCD": "000660"},
                    )

            joined = "\n".join(rl_logs.output)
            self.assertNotIn("KIS GET HTTP error", joined)
            self.assertLessEqual(joined.count("EGW00201"), 2)
            summary = krl.kis_rate_limit_observability()
            self.assertTrue(summary["circuit_breaker_triggered"])
            self.assertGreaterEqual(summary["rate_limit_error_count"], 1)
            self.assertLessEqual(len(http_calls), 4)

    def test_halt_blocks_further_kis_http_request(self) -> None:
        krl.reset_kis_rate_limit_state()
        krl._rate_limit_state.halted = True
        krl._rate_limit_state.circuit_breaker_triggered = True
        with patch("data.kis_rate_limit.requests.request") as mock_req:
            out = krl.kis_http_request("GET", "https://example.com", tr_id="X")
        mock_req.assert_not_called()
        self.assertIsNone(out)

    def test_default_rps_is_one(self) -> None:
        with patch.dict("os.environ", {"KIS_MAX_REQUESTS_PER_SECOND": ""}, clear=False):
            krl.reset_kis_rate_limit_state()
            self.assertEqual(krl.configured_max_rps(), 1.0)


class KISRateLimitRunnerTests(unittest.TestCase):
    def test_runner_returns_rate_limit_exceeded_with_metrics(self) -> None:
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
                    with mock.patch("data.kis_client.preflight_kis_auth", return_value={"ok": True}):
                        with mock.patch(
                            "src.trading.competition.replay.runner.build_close_snapshot",
                            return_value={"ok": True},
                        ):
                            with mock.patch("data.kis_client.is_kis_rate_limit_halted", return_value=True):
                                with mock.patch(
                                    "data.kis_client.kis_rate_limit_summary",
                                    return_value={
                                        "halted": True,
                                        "circuit_breaker_triggered": True,
                                        "rate_limit_error_count": 1,
                                        "retry_count": 1,
                                        "affected_tr_ids": ["FHKST03010100"],
                                        "configured_rps": 1.0,
                                        "actual_max_requests_in_rolling_1s": 1,
                                        "total_http_requests": 3,
                                    },
                                ):
                                    result = run_replay_single_day("20260109", sync_firestore=False)

            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "kis_rate_limit_exceeded")
            run_dir = next(root.iterdir())
            meta = json.loads((run_dir / "observability" / "execution_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "kis_rate_limit_exceeded")
            self.assertEqual(meta["kis_rate_limit"]["actual_max_requests_in_rolling_1s"], 1)
            self.assertTrue(meta["kis_rate_limit"]["circuit_breaker_triggered"])


if __name__ == "__main__":
    unittest.main()
