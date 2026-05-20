"""Render kr_market Jinja template to HTML (local preview / Firebase upload)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def render_kr_market(data: dict, output_path: str | Path) -> str:
    template_dir = Path(__file__).resolve().parent
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    html = env.get_template("template.html").render(**data)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out)


def main() -> None:
    base = Path(__file__).resolve().parent
    sample_path = base / "sample_data.json"
    out_path = base / "preview.html"
    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
    data = json.loads(sample_path.read_text(encoding="utf-8"))
    path = render_kr_market(data, out_path)
    print(path)


if __name__ == "__main__":
    main()
