"""Render report templates and export mobile-friendly HTML pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

TEMPLATE_MAP: dict[str, str] = {
    "us_during": "05_us_before.html",
    "us_close_kr_before": "02_kr_before.html",
    "kr_close_us_before": "04_kr_after.html",
    "us_after": "01_us_after.html",
    "kr_before": "02_kr_before.html",
    "kr_during": "03_kr_during.html",
    "kr_after": "04_kr_after.html",
    "us_before": "05_us_before.html",
    "weekly": "06_weekly.html",
}


def render_html(report_data: dict[str, Any]) -> str:
    """Render HTML from report data and mapped template."""
    template_dir = Path(__file__).resolve().parent / "templates"
    try:
        from jinja2 import Environment, FileSystemLoader  # type: ignore

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template_name = TEMPLATE_MAP.get(
            report_data.get("report_type", "kr_before"), "02_kr_before.html"
        )
        template = env.get_template(template_name)
        return template.render(**report_data)
    except Exception:
        # Fallback plain HTML when jinja2 is unavailable.
        return (
            "<html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
            "</head><body>"
            f"<h1>{report_data.get('report_type', 'report')}</h1>"
            f"<p>{report_data.get('date', '')}</p>"
            f"<p>{report_data.get('one_line_summary', '')}</p>"
            "</body></html>"
        )


def generate_html(report_data: dict[str, Any], output_path: str) -> str:
    """Render report_data to an HTML file and return the saved path."""
    html_content = render_html(report_data)
    output = Path(output_path).with_suffix(".html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_content, encoding="utf-8")
    return str(output)


def generate_pdf(report_data: dict[str, Any], output_path: str) -> str:
    """Backward-compatible alias. Reports are now saved as HTML pages."""
    return generate_html(report_data, output_path)
