# -*- coding: utf-8 -*-
"""pykrx safe wrappers — no uncaught JSON errors."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from src.trading.competition.replay.pykrx_safe import (
    classify_pykrx_error,
    krx_credentials_configured,
    safe_pykrx_call,
)


class PykrxSafeTests(unittest.TestCase):
    def test_classify_json_decode(self) -> None:
        code = classify_pykrx_error(json.JSONDecodeError("x", "", 0))
        self.assertEqual(code, "krx_empty_or_non_json_response")

    def test_safe_call_catches_json_error(self) -> None:
        def _boom() -> None:
            raise json.JSONDecodeError("Expecting value", "", 0)

        result, meta = safe_pykrx_call("test_call", _boom)
        self.assertIsNone(result)
        self.assertFalse(meta["ok"])
        self.assertEqual(meta["error_code"], "krx_empty_or_non_json_response")

    def test_krx_credentials_env(self) -> None:
        with patch.dict(os.environ, {"KRX_ID": "u", "KRX_PW": "p"}, clear=False):
            self.assertTrue(krx_credentials_configured())
        with patch.dict(os.environ, {"KRX_ID": "", "KRX_PW": ""}, clear=False):
            self.assertFalse(krx_credentials_configured())


if __name__ == "__main__":
    unittest.main()
