# -*- coding: utf-8
"""Rebuild docs/simple-replay-data index from local completed runs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading.simple_replay.publish import rebuild_index
from src.trading.simple_replay.storage import list_local_runs
from src.trading.simple_replay.publish import publish_run


def main() -> int:
    for m in list_local_runs():
        if m.get("status") == "completed" and m.get("run_id"):
            publish_run(str(m["run_id"]))
    path = rebuild_index()
    print(f"Published index: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
