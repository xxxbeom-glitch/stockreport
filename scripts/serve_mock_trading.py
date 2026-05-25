# -*- coding: utf-8 -*-
"""정적 파일 + 투자 상태 API (Firestore/로컬 JSON)."""

from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.trading_web_sync import build_cumulative_trading_payload
from agents.mock_trading.weekly_recommendations_store import (
    append_virtual_buy,
    load_weekly_recommendations,
)


class MockTradingHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        if args and str(args[0]).startswith("GET /api/"):
            return
        super().log_message(format, *args)

    def do_OPTIONS(self) -> None:
        self._cors()
        self.send_response(204)
        self.end_headers()

    def _parse_week_id(self, default: str = "2026-W21") -> str:
        return self._query_param("week_id", default)

    def _query_param(self, key: str, default: str = "") -> str:
        parsed = parse_qs(urlparse(self.path).query)
        vals = parsed.get(key)
        if vals and vals[0]:
            return vals[0]
        return default

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/weekly-recommendations":
            self._handle_get_weekly()
            return
        if path == "/api/trading-display":
            self._handle_get_trading_display()
            return
        if path == "/api/trading-competition/dashboard":
            self._handle_competition_dashboard()
            return
        if path == "/api/trading-competition/weekly-reports":
            self._handle_competition_weekly_reports()
            return
        if path == "/api/trading-competition/notifications":
            self._handle_competition_notifications()
            return
        if path == "/api/trading-competition/replay/runs":
            self._handle_competition_replay_runs()
            return
        if path == "/api/trading-competition/replay/dashboard":
            self._handle_competition_replay_dashboard()
            return
        if path == "/api/trading-competition/replay/campaigns":
            self._handle_competition_replay_campaigns()
            return
        if path == "/api/trading-competition/simple-replay/runs":
            self._handle_simple_replay_runs()
            return
        if path == "/api/trading-competition/simple-replay/dashboard":
            self._handle_simple_replay_dashboard()
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/virtual-buy":
            self._handle_virtual_buy()
            return
        if path == "/api/mock-trading/auto-ops":
            self._handle_auto_ops()
            return
        if path == "/api/mock-trading/scheduled-judgment":
            self._handle_scheduled_judgment()
            return
        if path == "/api/mock-trading/execute-pending":
            self._handle_execute_pending()
            return
        if path == "/api/mock-trading/realtime-watch":
            self._handle_realtime_watch()
            return
        if path == "/api/mock-trading/intraday-judgment":
            self._handle_intraday_judgment()
            return
        if path == "/api/trading-competition/session":
            self._handle_competition_session()
            return
        self.send_error(404)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_get_weekly(self) -> None:
        week_id = self._parse_week_id()
        doc = load_weekly_recommendations(week_id)
        if not doc:
            self._json_response(404, {"ok": False, "error": "weekly recommendations not found"})
            return
        self._json_response(200, {"ok": True, "week_id": week_id, "weekly": doc})

    def _handle_get_trading_display(self) -> None:
        data = build_cumulative_trading_payload()
        self._json_response(
            200,
            {
                "ok": True,
                "scope": "cumulative",
                "data": data,
            },
        )

    def _handle_virtual_buy(self) -> None:
        body = self._read_json_body()
        week_id = str(body.get("week_id") or self._parse_week_id())
        record = body.get("record")
        if not isinstance(record, dict):
            self._json_response(400, {"ok": False, "error": "record object required"})
            return
        saved = append_virtual_buy(week_id, record)
        self._json_response(200 if saved.get("ok") else 500, saved)

    def _handle_auto_ops(self) -> None:
        from agents.mock_trading.auto_operations import run_auto_operations

        body = self._read_json_body()
        result = run_auto_operations(force_judgment=bool(body.get("force_judgment")))
        self._json_response(200 if result.get("ok") else 400, result)

    def _handle_scheduled_judgment(self) -> None:
        from agents.mock_trading.scheduled_judgment import run_scheduled_judgment

        body = self._read_json_body()
        result = run_scheduled_judgment(
            entry_type=body.get("entry_type"),
            dry_run=bool(body.get("dry_run")),
            force=bool(body.get("force")),
        )
        self._json_response(200 if result.get("ok") else 400, result)

    def _handle_execute_pending(self) -> None:
        from agents.mock_trading.virtual_buy_executor import process_limit_orders

        result = process_limit_orders()
        self._json_response(200 if result.get("ok") else 500, result)

    def _handle_realtime_watch(self) -> None:
        from agents.mock_trading.realtime_watch import run_watch_cycle

        body = self._read_json_body()
        result = run_watch_cycle(
            min_change_rate=float(body.get("min_change_rate") or 3.0),
            include_dart=body.get("include_dart", True) is not False,
            persist_candidates=body.get("persist_candidates", True) is not False,
        )
        self._json_response(200 if result.get("ok") else 500, result)

    def _handle_intraday_judgment(self) -> None:
        from agents.mock_trading.intraday_alert_judgment import process_open_intraday_candidates

        body = self._read_json_body()
        result = process_open_intraday_candidates(
            dry_run=bool(body.get("dry_run")),
            limit=int(body.get("limit") or 5),
        )
        self._json_response(200 if result.get("ok") else 500, result)

    def _handle_competition_dashboard(self) -> None:
        from src.trading.competition.dashboard.payload import build_dashboard_payload

        self._json_response(200, {"ok": True, "dataSource": "live", "data": build_dashboard_payload()})

    def _handle_competition_replay_runs(self) -> None:
        from src.trading.competition.dashboard.replay_payload import list_replay_runs

        self._json_response(200, {"ok": True, "dataSource": "replay_index", "runs": list_replay_runs()})

    def _handle_competition_replay_dashboard(self) -> None:
        from src.trading.competition.dashboard.replay_payload import build_replay_dashboard_payload

        replay_run_id = self._query_param("replay_run_id").strip()
        campaign_id = self._query_param("campaign").strip() or None
        if not replay_run_id:
            self._json_response(400, {"ok": False, "error": "replay_run_id required"})
            return
        try:
            data = build_replay_dashboard_payload(replay_run_id, campaign_id=campaign_id)
        except FileNotFoundError as exc:
            self._json_response(404, {"ok": False, "error": str(exc)})
            return
        self._json_response(
            200,
            {
                "ok": True,
                "dataSource": "replay",
                "replayRunId": replay_run_id,
                "campaignId": data.get("campaignId"),
                "data": data,
            },
        )

    def _handle_competition_replay_campaigns(self) -> None:
        import json as _json

        root = ROOT / "data" / "competition" / "replay" / "campaigns"
        campaigns: list[dict[str, Any]] = []
        if root.is_dir():
            for p in sorted(root.glob("*/manifest.json"), reverse=True):
                try:
                    campaigns.append(_json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
        self._json_response(200, {"ok": True, "dataSource": "replay_campaigns", "campaigns": campaigns})

    def _handle_competition_weekly_reports(self) -> None:
        import json as _json

        root = ROOT / "data" / "competition" / "weekly_reports"
        reports: dict[str, Any] = {}
        if root.is_dir():
            for p in sorted(root.glob("*.json")):
                reports[p.stem] = _json.loads(p.read_text(encoding="utf-8"))
        self._json_response(200, {"ok": True, "weeklyReports": reports})

    def _handle_competition_notifications(self) -> None:
        from src.trading.competition.storage.journal import load_notifications

        self._json_response(200, {"ok": True, "notifications": load_notifications()})

    def _handle_simple_replay_runs(self) -> None:
        from src.trading.simple_replay.api import list_runs_for_dashboard

        self._json_response(
            200,
            {"ok": True, "dataSource": "simple_replay_index", "runs": list_runs_for_dashboard()},
        )

    def _handle_simple_replay_dashboard(self) -> None:
        from src.trading.simple_replay.api import load_dashboard_for_run

        run_id = self._query_param("run_id").strip()
        if not run_id:
            self._json_response(400, {"ok": False, "error": "run_id required"})
            return
        try:
            data = load_dashboard_for_run(run_id)
        except FileNotFoundError:
            self._json_response(404, {"ok": False, "error": "simple_replay_run_not_found"})
            return
        self._json_response(
            200,
            {"ok": True, "dataSource": "simple_replay", "runId": run_id, "data": data},
        )

    def _handle_competition_session(self) -> None:
        from src.trading.competition.ops.session import run_competition_session

        body = self._read_json_body()
        session_id = str(body.get("session_id") or "api_session")
        result = run_competition_session(
            session_id,
            dry_run=bool(body.get("dry_run")),
            force_mock=body.get("force_mock", True) is not False,
            persist_triggers=not bool(body.get("dry_run")),
            relax_entry_filter=bool(body.get("relax_entry_filter")),
        )
        self._json_response(200 if result.get("ok") else 500, result)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.bind, args.port), MockTradingHandler)
    print(f"Serving {ROOT} on http://{args.bind}:{args.port}/")
    print(f"Web UI: http://127.0.0.1:{args.port}/template/kr_trading/")
    print("API:")
    print("  GET  /api/trading-display")
    print("  GET  /api/weekly-recommendations?week_id=2026-W21")
    print("  POST /api/virtual-buy")
    print("  POST /api/mock-trading/auto-ops")
    print("  POST /api/mock-trading/scheduled-judgment")
    print("  POST /api/mock-trading/execute-pending")
    print("  POST /api/mock-trading/realtime-watch")
    print("  POST /api/mock-trading/intraday-judgment")
    print("  GET  /api/trading-competition/dashboard")
    print("  GET  /api/trading-competition/replay/runs")
    print("  GET  /api/trading-competition/replay/dashboard?replay_run_id=...")
    print("  GET  /api/trading-competition/simple-replay/runs")
    print("  GET  /api/trading-competition/simple-replay/dashboard?run_id=...")
    print("  GET  /api/trading-competition/weekly-reports")
    print("  GET  /api/trading-competition/notifications")
    print("  POST /api/trading-competition/session")
    print(f"  Competition UI: http://127.0.0.1:{args.port}/template/dashboard_desktop/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
