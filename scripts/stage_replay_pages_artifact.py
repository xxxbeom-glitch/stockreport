# -*- coding: utf-8
"""Stage minimal GitHub Pages artifact (dashboard + public REPLAY JSON only)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "_pages_staging"


def stage_pages_artifact(out_dir: Path) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    copied: list[str] = []

    root_index = ROOT / "index.html"
    if root_index.is_file():
        shutil.copy2(root_index, out_dir / "index.html")
        copied.append("index.html")

    dash_src = ROOT / "template" / "dashboard_desktop"
    if dash_src.is_dir():
        shutil.copytree(dash_src, out_dir / "template" / "dashboard_desktop")
        copied.append("template/dashboard_desktop/")

    replay_public = ROOT / "docs" / "replay-data"
    if replay_public.is_dir():
        shutil.copytree(replay_public, out_dir / "docs" / "replay-data")
        copied.append("docs/replay-data/")

    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    forbidden_prefixes = ("src/", "tests/", "scripts/", "data/competition/")
    bad = []
    for path in out_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(out_dir).as_posix()
        for prefix in forbidden_prefixes:
            if rel.startswith(prefix):
                bad.append(rel)
    if bad:
        raise RuntimeError(f"Pages staging must not include: {bad[:5]}")

    return {"ok": True, "out_dir": str(out_dir), "copied": copied}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--manifest-out", default="")
    args = parser.parse_args()
    out = Path(args.out)
    result = stage_pages_artifact(out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.manifest_out:
        Path(args.manifest_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
