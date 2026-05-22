# -*- coding: utf-8 -*-
"""정적 파일 + 투자 상태 API (Firestore/로컬 JSON)."""

from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.trading_state_store import load_trading_state, save_trading_state
from agents.mock_trading.trading_web_sync import (
    build_trading_data,
    build_trading_data_from_firestore_doc,
)
from agents.mock_trading.weekly_recommendations_store import (
    append_virtual_buy,
    append_virtual_take_profit,
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
        query = urlparse(self.path).query
        week_id = default
        for part in query.split("&"):
            if part.startswith("week_id="):
                week_id = part.split("=", 1)[1]
        return week_id

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/trading-state":
            self._handle_get_state()
            return
        if path == "/api/weekly-recommendations":
            self._handle_get_weekly()
            return
        if path == "/api/trading-display":
            self._handle_get_trading_display()
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/trading-state":
            self._handle_post_state()
            return
        if path == "/api/virtual-buy":
            self._handle_virtual_buy()
            return
        if path == "/api/virtual-take-profit":
            self._handle_virtual_take_profit()
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

    def _handle_get_state(self) -> None:
        doc = load_trading_state(self._parse_week_id())
        self._json_response(200, {"ok": True, "state": doc})

    def _handle_get_weekly(self) -> None:
        week_id = self._parse_week_id()
        doc = load_weekly_recommendations(week_id)
        if not doc:
            self._json_response(404, {"ok": False, "error": "weekly recommendations not found"})
            return
        self._json_response(200, {"ok": True, "week_id": week_id, "weekly": doc})

    def _handle_get_trading_display(self) -> None:
        week_id = self._parse_week_id()
        weekly_doc = load_weekly_recommendations(week_id)
        if weekly_doc:
            data = build_trading_data_from_firestore_doc(weekly_doc)
            self._json_response(
                200,
                {
                    "ok": True,
                    "week_id": week_id,
                    "data": data,
                    "weekly": {
                        "persist_backend": weekly_doc.get("persist_backend"),
                        "firestore_path": weekly_doc.get("firestore_path"),
                        "uniqueRecommendationCount": weekly_doc.get(
                            "uniqueRecommendationCount"
                        ),
                    },
                },
            )
            return
        data = build_trading_data()
        self._json_response(
            200,
            {
                "ok": True,
                "week_id": week_id,
                "data": data,
                "weekly": {"persist_backend": "local_json_files"},
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

    def _handle_virtual_take_profit(self) -> None:
        body = self._read_json_body()
        week_id = str(body.get("week_id") or self._parse_week_id())
        record = body.get("record")
        if not isinstance(record, dict):
            self._json_response(400, {"ok": False, "error": "record object required"})
            return
        saved = append_virtual_take_profit(week_id, record)
        self._json_response(200 if saved.get("ok") else 500, saved)

    def _handle_post_state(self) -> None:
        body = self._read_json_body()
        week_id = str(body.get("week_id") or "2026-W21")
        holdings = body.get("holdings")
        if not isinstance(holdings, list):
            self._json_response(400, {"ok": False, "error": "holdings array required"})
            return
        saved = save_trading_state(week_id, holdings)
        self._json_response(200, {"ok": True, "state": saved})


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
    print("  GET  /api/trading-display?week_id=2026-W21")
    print("  GET  /api/weekly-recommendations?week_id=2026-W21")
    print("  GET/POST /api/trading-state?week_id=2026-W21")
    print("  POST /api/virtual-buy | /api/virtual-take-profit")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
