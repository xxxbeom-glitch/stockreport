# -*- coding: utf-8 -*-
"""KIS token auth — single issue, thread-safe cache, safe error logging."""

from __future__ import annotations

import logging
import threading
import unittest
from unittest.mock import MagicMock, patch

from data import kis_client as kc


class KISClientAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        kc.reset_kis_auth_state(clear_token=True)
        kc.reset_kis_rate_limit()
        if kc._default_client is not None:
            kc._default_client._token_issue_calls = 0

    def test_safe_kis_error_parses_msg_fields(self) -> None:
        res = MagicMock()
        res.status_code = 403
        res.text = '{"msg_cd":"EGW00123","msg1":"유효하지 않은 AppKey"}'
        res.json.return_value = {"msg_cd": "EGW00123", "msg1": "유효하지 않은 AppKey"}
        meta = kc._safe_kis_error_from_response(res)
        self.assertEqual(meta["http_status"], 403)
        self.assertEqual(meta["msg_cd"], "EGW00123")
        self.assertIn("AppKey", meta["msg1"])

    def test_concurrent_ensure_token_issues_once(self) -> None:
        client = kc.KISClient()
        client._memory_token = None
        client._memory_issued_at = None
        calls: list[int] = []

        def _fake_issue() -> dict:
            calls.append(1)
            client._memory_token = "tok_test"
            client._memory_issued_at = kc._now()
            return {"ok": True, "http_status": 200}

        with patch.object(kc.config, "KIS_APP_KEY", "key123456"):
            with patch.object(kc.config, "KIS_APP_SECRET", "secret" * 10):
                with patch.object(client, "_read_cached_token", return_value=None):
                    with patch.object(client, "_issue_token_http", side_effect=_fake_issue):

                        def _worker() -> str | None:
                            return client.ensure_token()

                        threads = [threading.Thread(target=_worker) for _ in range(12)]
                        for t in threads:
                            t.start()
                        for t in threads:
                            t.join()
        self.assertEqual(len(calls), 1)

    def test_auth_failed_latch_prevents_repeated_token_issue(self) -> None:
        client = kc.KISClient()
        calls: list[int] = []

        def _fail_issue() -> dict:
            calls.append(1)
            return {
                "ok": False,
                "error": "kis_auth_failed",
                "http_status": 403,
                "msg_cd": "EGW00123",
                "msg1": "denied",
            }

        with patch.object(kc.config, "KIS_APP_KEY", "key123456"):
            with patch.object(kc.config, "KIS_APP_SECRET", "secret" * 10):
                with patch.object(client, "_read_cached_token", return_value=None):
                    with patch.object(client, "_issue_token_http", side_effect=_fail_issue):

                        def _worker() -> str | None:
                            return client.ensure_token()

                        threads = [threading.Thread(target=_worker) for _ in range(20)]
                        for t in threads:
                            t.start()
                        for t in threads:
                            t.join()
        self.assertEqual(len(calls), 1)
        self.assertTrue(client.is_auth_failed())

    def test_preflight_failure_marks_auth_failed_and_blocks_get(self) -> None:
        client = kc.KISClient()
        client.last_auth_error = {
            "ok": False,
            "error": "kis_auth_failed",
            "http_status": 403,
            "msg_cd": "E001",
            "msg1": "denied",
        }
        old = kc._default_client
        try:
            with patch.object(kc.config, "KIS_APP_KEY", "k"):
                with patch.object(kc.config, "KIS_APP_SECRET", "s"):
                    with patch.object(client, "ensure_token", return_value=None):
                        kc._default_client = client
                        client._auth_failed = True
                        out = kc.preflight_kis_auth()
                        self.assertFalse(out["ok"])
                        self.assertEqual(out["error"], "kis_auth_failed")
                        self.assertIsNone(client.get_price("005930"))
        finally:
            kc._default_client = old

    def test_successful_token_reused_for_multiple_price_calls(self) -> None:
        client = kc.KISClient()
        client._memory_token = "tok_cached"
        client._memory_issued_at = kc._now()
        issue_calls: list[int] = []

        def _track_issue() -> dict:
            issue_calls.append(1)
            return {"ok": True, "http_status": 200}

        sample = {"output": {"stck_prpr": "70000", "prdy_ctrt": "1.0", "acml_vol": "100"}}
        old = kc._default_client
        try:
            with patch.object(kc.config, "KIS_APP_KEY", "k"):
                with patch.object(kc.config, "KIS_APP_SECRET", "s"):
                    with patch.object(client, "_issue_token_http", side_effect=_track_issue):
                        with patch.object(client, "_get", return_value=sample):
                            kc._default_client = client
                            for code in ("005930", "000660", "035420"):
                                client.get_price(code)
        finally:
            kc._default_client = old
        self.assertEqual(issue_calls, [])

    def test_token_refresh_on_api_auth_error_only_once(self) -> None:
        client = kc.KISClient()
        client._memory_token = "old_tok"
        client._memory_issued_at = kc._now()
        refresh_calls: list[bool] = []
        responses = [
            MagicMock(status_code=403, text='{"msg_cd":"EGW00123","msg1":"expired"}'),
            MagicMock(status_code=200, text='{"rt_cd":"0","output":{"stck_prpr":"70000"}}'),
        ]
        responses[0].json.return_value = {"msg_cd": "EGW00123", "msg1": "expired"}
        responses[1].json.return_value = {"rt_cd": "0", "output": {"stck_prpr": "70000"}}

        def _fake_refresh(*, force_refresh: bool = False) -> str | None:
            refresh_calls.append(force_refresh)
            if force_refresh:
                client._memory_token = "new_tok"
            return client._memory_token

        with patch.object(client, "ensure_token", side_effect=_fake_refresh):
            with patch("data.kis_client.kis_http_request", side_effect=responses):
                data = client._get(
                    "/uapi/domestic-stock/v1/quotations/inquire-price",
                    "FHKST01010100",
                    {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"},
                )
        self.assertEqual(refresh_calls.count(True), 1)
        self.assertEqual(data.get("rt_cd"), "0")

    def test_issue_token_logs_safe_fields_only(self) -> None:
        client = kc.KISClient()
        secret = "super_secret_value_12345"
        res = MagicMock()
        res.status_code = 403
        res.text = f'{{"msg_cd":"EGW00123","msg1":"invalid","appsecret":"{secret}"}}'
        res.json.return_value = {"msg_cd": "EGW00123", "msg1": "invalid", "appsecret": secret}

        with patch.object(kc.config, "KIS_APP_KEY", "appkey123"):
            with patch.object(kc.config, "KIS_APP_SECRET", secret):
                with patch("data.kis_client.kis_http_request", return_value=res):
                    with self.assertLogs("data.kis_client", level="WARNING") as captured:
                        out = client._issue_token_http()
        joined = "\n".join(captured.output)
        self.assertFalse(out["ok"])
        self.assertIn("403", joined)
        self.assertTrue("EGW00123" in joined or "EGW00103" in joined or "error_code" in joined)
        self.assertNotIn(secret, joined)
        self.assertNotIn("appkey123", joined)

    def test_preflight_returns_kis_auth_failed_without_token(self) -> None:
        client = kc.KISClient()
        client.last_auth_error = {"ok": False, "msg_cd": "E001", "msg1": "denied"}
        old = kc._default_client
        try:
            with patch.object(kc.config, "KIS_APP_KEY", "k"):
                with patch.object(kc.config, "KIS_APP_SECRET", "s"):
                    with patch.object(client, "ensure_token", return_value=None):
                        kc._default_client = client
                        client._auth_failed = True
                        out = kc.preflight_kis_auth()
            self.assertFalse(out["ok"])
            self.assertEqual(out["error"], "kis_auth_failed")
            self.assertEqual(out["msg_cd"], "E001")
        finally:
            kc._default_client = old

    def test_credentials_diagnostics_no_secret_values(self) -> None:
        with patch.object(kc.config, "KIS_APP_KEY", "abcdefghij"):
            with patch.object(kc.config, "KIS_APP_SECRET", "x" * 20):
                diag = kc.credentials_diagnostics()
        self.assertTrue(diag["configured"])
        self.assertEqual(diag["app_key_len"], 10)
        self.assertEqual(diag["app_secret_len"], 20)
        self.assertEqual(diag["endpoint_mode"], "production")
        self.assertNotIn("app_key", diag)
        self.assertNotIn("app_secret", diag)


class KISAuthFailFastIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        kc.reset_kis_auth_state(clear_token=True)

    def test_enrich_records_stops_when_auth_failed(self) -> None:
        from src.trading.competition.replay import universe_replay as ur

        records = [
            {"ticker": f"{i:06d}", "name": f"테스트{i}", "market": "KOSPI", "data_sources": []}
            for i in range(10)
        ]
        kc._default_client._auth_failed = True
        with patch("src.trading.competition.replay.data_provider._kis_ready", return_value=True):
            with patch.object(ur, "_enrich_one_record") as mock_one:
                enriched, errors, target, stopped, _ = ur.enrich_records_for_trading_date(
                    records, "20260109"
                )
        mock_one.assert_not_called()
        self.assertEqual(enriched, 0)
        self.assertIn("kis_auth_failed", errors)
        self.assertEqual(target, 0)


if __name__ == "__main__":
    unittest.main()
