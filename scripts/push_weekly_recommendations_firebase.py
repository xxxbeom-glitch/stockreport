# -*- coding: utf-8 -*-
"""로컬 merged/weekly JSON → Firestore weeklyRecommendations/{week_id} (AI 재실행 없음)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.mock_trading.weekly_recommendations_store import save_weekly_from_local_files


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    result = save_weekly_from_local_files()
    print(f"week_id={result.get('week_id')}")
    print(f"path={result.get('firestore_path')}")
    print(f"unique={result.get('unique_count')}")
    print(f"backend={result.get('persist_backend')}")
    print(f"ok={result.get('ok')}")
    if result.get("error"):
        print(f"error={result.get('error')}")
    fb = result.get("firebase") or {}
    if isinstance(fb, dict) and fb.get("error"):
        print(f"firebase_detail={fb.get('error')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
