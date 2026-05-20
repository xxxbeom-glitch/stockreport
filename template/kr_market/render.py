"""Render kr_market Jinja template to HTML (local preview / Firebase upload)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from jinja2 import Environment, FileSystemLoader

from utils.ui_comment import format_ui_comment


def render_kr_market(data: dict, output_path: str | Path) -> str:
    template_dir = Path(__file__).resolve().parent
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    env.filters["ui_comment"] = format_ui_comment
    html = env.get_template("template.html").render(**data)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out)


def main() -> None:
    base = Path(__file__).resolve().parent
    sample_path = base / "sample_data.json"
    out_path = base / "index.html"
    for arg in sys.argv[1:]:
        if arg.startswith("-") or arg in ("--live", "--verify"):
            continue
        if arg.endswith(".html"):
            out_path = Path(arg)
    if "--live" in sys.argv:
        from template.kr_market.build_index import build_index

        live_out = out_path
        for arg in sys.argv[1:]:
            if arg.endswith(".html"):
                live_out = Path(arg)
        path = build_index(output=live_out)
        print(path)
        return

    from template.kr_market.report_adapter import build_kr_market_context

    if "--verify" in sys.argv:
        from template.kr_market.report_adapter import build_watchlist_verify_report_data

        report_data = build_watchlist_verify_report_data()
    else:
        report_data = json.loads(sample_path.read_text(encoding="utf-8"))
        if not report_data.get("stock_analysis"):
            from template.kr_market.report_adapter import build_static_preview_report_data

            report_data = build_static_preview_report_data()
    ctx = build_kr_market_context(report_data, pipeline=None)
    path = render_kr_market(ctx, out_path)
    print(path)


if __name__ == "__main__":
    main()
