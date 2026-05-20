"""Regenerate sample_data.json from build_static_preview_report_data + build_kr_market_context."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from template.kr_market.report_adapter import (
    build_kr_market_context,
    build_static_preview_report_data,
)


def main() -> None:
    base = Path(__file__).resolve().parent
    out = base / "sample_data.json"
    ctx = build_kr_market_context(build_static_preview_report_data(), pipeline=None)
    payload = {k: v for k, v in ctx.items() if not k.startswith("_")}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
