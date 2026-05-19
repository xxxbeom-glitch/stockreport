"""Render report templates and export mobile-friendly HTML pages."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
    except ImportError as exc:
        msg = (
            "jinja2 is required for report HTML rendering. "
            "Install dependencies: pip install -r requirements.txt"
        )
        logger.error(msg)
        raise ImportError(msg) from exc

    template_name = TEMPLATE_MAP.get(
        report_data.get("report_type", "kr_before"), "02_kr_before.html"
    )
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    try:
        template = env.get_template(template_name)
        return template.render(**report_data)
    except Exception as exc:
        logger.exception("Template render failed (%s): %s", template_name, exc)
        raise


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
