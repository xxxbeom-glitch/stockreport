# -*- coding: utf-8 -*-
"""KIS token auth — single issue, thread-safe cache, safe error logging."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

from data import kis_client as kc


class KISClientAuthTests(unittest.TestCase):
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

    def test_preflight_returns_kis_auth_failed_without_token(self) -> None:
        client = kc.KISClient()
        client.last_auth_error = {"ok": False, "msg_cd": "E001", "msg1": "denied"}
        old = kc._default_client
        try:
            with patch.object(kc.config, "KIS_APP_KEY", "k"):
                with patch.object(kc.config, "KIS_APP_SECRET", "s"):
                    with patch.object(client, "ensure_token", return_value=None):
                        kc._default_client = client
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
        self.assertNotIn("app_key", diag)


if __name__ == "__main__":
    unittest.main()
