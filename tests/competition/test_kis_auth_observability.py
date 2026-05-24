"""REPLAY runner — KIS auth failure observability without traceback."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.trading.competition.replay.observability import RunObservability, _kis_auth_observability_fields
from src.trading.competition.replay.runner import run_replay_single_day


class KISAuthObservabilityTests(unittest.TestCase):
    def test_log_api_connection_accepts_token_issue_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "replay" / "replay_20260109_test01"
            root.mkdir(parents=True)
            with mock.patch(
                "src.trading.competition.replay.observability.replay_run_dir",
                return_value=root,
            ):
                obs = RunObservability("replay_20260109_test01", trading_date="20260109")
                obs.log_api_connection(
                    "kis_auth",
                    ok=False,
                    token_issue_calls=1,
                    http_status=403,
                    error_code="EGW00103",
                    endpoint_mode="production",
                )
                events_path = root / "observability" / "pipeline_events.jsonl"
                lines = events_path.read_text(encoding="utf-8").strip().splitlines()
                rec = json.loads(lines[-1])
            self.assertEqual(rec["stage"], "api_connection")
            self.assertEqual(rec["service"], "kis_auth")
            self.assertEqual(rec["token_issue_calls"], 1)
            self.assertEqual(rec["http_status"], 403)
            self.assertEqual(rec["error_code"], "EGW00103")
            self.assertEqual(rec["endpoint_mode"], "production")

    def test_preflight_403_finalizes_without_traceback(self) -> None:
        failed_auth = {
            "ok": False,
            "error": "kis_auth_failed",
            "http_status": 403,
            "error_code": "EGW00103",
            "error_description": "유효하지 않은 AppKey입니다.",
            "endpoint_mode": "production",
            "base_url": "https://openapi.koreainvestment.com:9443",
            "token_issue_calls": 1,
            "app_key_len": 36,
            "app_secret_len": 36,
            "configured": True,
        }
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
                        return_value=failed_auth,
                    ):
                        with mock.patch(
                            "src.trading.competition.replay.runner.build_close_snapshot",
                        ) as mock_snapshot:
                            result = run_replay_single_day("20260109", sync_firestore=False)

            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "kis_auth_failed")
            mock_snapshot.assert_not_called()

            run_dir = next(root.iterdir())
            meta = json.loads((run_dir / "observability" / "execution_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "kis_auth_failed")
            self.assertEqual(meta["kis_auth"]["error"], "kis_auth_failed")
            self.assertEqual(meta["kis_auth"]["http_status"], 403)
            self.assertEqual(meta["kis_auth"]["error_code"], "EGW00103")
            self.assertEqual(meta["kis_auth"]["endpoint_mode"], "production")
            self.assertEqual(meta["kis_auth"]["token_issue_calls"], 1)

            events = (run_dir / "observability" / "pipeline_events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"token_issue_calls": 1', events)
            self.assertIn('"service": "kis_auth"', events)

    def test_kis_auth_observability_fields_exclude_secrets(self) -> None:
        safe = _kis_auth_observability_fields(
            {
                "error": "kis_auth_failed",
                "appkey": "must-not-appear",
                "app_secret": "must-not-appear",
                "token_issue_calls": 1,
                "endpoint_mode": "production",
            }
        )
        self.assertEqual(safe["token_issue_calls"], 1)
        self.assertNotIn("appkey", safe)
        self.assertNotIn("app_secret", safe)


if __name__ == "__main__":
    unittest.main()
