# -*- coding: utf-8 -*-
"""주간 추천 Firebase 저장·덮어쓰기·웹 API 로드 검증."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.weekly_recommendations_store import (
    COLLECTION,
    MERGED_PATH,
    WEEKLY_PATH,
    load_weekly_recommendations,
    save_weekly_from_local_files,
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _http_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    week_id = "2026-W21"
    port = os.environ.get("MOCK_TRADING_PORT", "8090")
    base = f"http://127.0.0.1:{port}"

    merged = _load(MERGED_PATH)
    weekly = _load(WEEKLY_PATH)
    results: list[tuple[str, bool, str]] = []

    before = load_weekly_recommendations(week_id)
    had_firestore = (before or {}).get("persist_backend") == "firestore"
    results.append(
        (
            "1. 작업 전 Firebase 문서 존재",
            had_firestore,
            f"backend={(before or {}).get('persist_backend', 'none')}",
        )
    )

    push1 = save_weekly_from_local_files(week_id)
    ok_push = (
        int(push1.get("unique_count") or 0) == 15
        and push1.get("persist_backend") in ("firestore", "local_mirror")
    )
    results.append(
        (
            "2. 로컬 JSON → weeklyRecommendations 저장",
            ok_push,
            f"backend={push1.get('persist_backend')}, path={push1.get('firestore_path')}",
        )
    )

    loaded = load_weekly_recommendations(week_id) or {}
    n_merged = len(loaded.get("mergedRecommendations") or [])
    n_agents = len(loaded.get("agentRecommendations") or [])
    backend = loaded.get("persist_backend")
    ok_load = (
        n_merged == 15
        and n_agents == 4
        and int(loaded.get("uniqueRecommendationCount") or 0) == 15
    )
    results.append(
        (
            "3. 재로드(15종·에이전트4)",
            ok_load,
            f"merged={n_merged}, agents={n_agents}, backend={backend}",
        )
    )

    import time

    time.sleep(1)
    push2 = save_weekly_from_local_files(week_id)
    loaded2 = load_weekly_recommendations(week_id) or {}
    ok_overwrite = (
        push2.get("persist_backend") in ("firestore", "local_mirror")
        and loaded2.get("firestore_path") == f"{COLLECTION}/{week_id}"
        and loaded2.get("updatedAt") != loaded.get("updatedAt")
    )
    results.append(
        (
            "4. 동일 week_id 재저장=갱신(단일 문서)",
            ok_overwrite,
            f"updatedAt1={loaded.get('updatedAt')}, updatedAt2={loaded2.get('updatedAt')}",
        )
    )

    api_ok = False
    api_detail = "serve_mock_trading.py 미기동"
    try:
        url = base + "/api/trading-display"
        body = _http_json(url)
        data = body.get("data") or {}
        holdings = data.get("holdings") or []
        agents = data.get("agents") or []
        weekly_meta = body.get("weekly") or {}
        api_ok = (
            body.get("ok")
            and len(holdings) == 15
            and len(agents) == 4
            and weekly_meta.get("persist_backend") in ("firestore", "local_mirror", "local_json_files")
        )
        api_detail = (
            f"holdings={len(holdings)}, agents={len(agents)}, "
            f"source={(data.get('pageMeta') or {}).get('data_source')}"
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        api_detail = str(exc)

    results.append(("5. 웹 API 새로고침 로드", api_ok, api_detail))

    print("=== 주간 추천 Firebase 검증 ===\n")
    failed = 0
    for name, ok, detail in results:
        mark = "성공" if ok else "실패"
        if not ok:
            failed += 1
        print(f"[{mark}] {name}")
        print(f"       {detail}\n")

    if failed and not ok_push:
        print("참고: Firebase 미연결 시 local_mirror만 저장됩니다.")
        print("      FIREBASE_KEY_PATH 파일 또는 FIREBASE_SERVICE_ACCOUNT 설정 필요.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
