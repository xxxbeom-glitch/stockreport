"""DART API key / skip behavior."""

from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

from data import api_env, dart_client


class TestDartClient(unittest.TestCase):
    def setUp(self) -> None:
        dart_client._WARNED_NO_KEY = False
        dart_client._STOCK_TO_CORP = None
        api_env._DOTENV_DONE = True

    def test_missing_key_skips_with_warning(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertLogs("data.dart_client", level="WARNING") as logs:
                out = dart_client.fetch_disclosure_summary("005930")
            self.assertIsNone(out)
            self.assertTrue(any("DART_API_KEY" in m for m in logs.output))
            self.assertFalse(any("6b315eff" in m for m in logs.output))

    def test_collect_skips_all_when_unconfigured(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertLogs("data.dart_client", level="WARNING"):
                result = dart_client.collect_dart_disclosures(["005930", "000660"])
            self.assertEqual(result, {"005930": None, "000660": None})

    @patch("data.dart_client._dart_get")
    @patch("data.dart_client._resolve_corp_code", return_value="00126380")
    def test_fetch_summary_with_key(
        self,
        _mock_corp: unittest.mock.MagicMock,
        mock_get: unittest.mock.MagicMock,
    ) -> None:
        mock_get.return_value = {
            "status": "000",
            "list": [{"report_nm": "분기보고서"}],
        }
        with patch.dict("os.environ", {"DART_API_KEY": "test-key-secret"}, clear=False):
            dart_client._STOCK_TO_CORP = {}
            out = dart_client.fetch_disclosure_summary("005930")
        self.assertIn("분기보고서", out or "")
        params = mock_get.call_args[0][1]
        self.assertEqual(params.get("corp_code"), "00126380")
        self.assertNotIn("test-key-secret", str(params))


if __name__ == "__main__":
    unittest.main()
