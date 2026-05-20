"""Build template/kr_market/index.html from live pipeline (KR only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv()

from agents import run_agent_pipeline
from data.pipeline import run_pipeline_as_dict
from main import DEFAULT_REPORT_TYPE, _build_company_reports, _build_report_data
from template.kr_market.report_adapter import render_kr_market_page
from utils.token_logger import TokenLogger


def build_index(
    report_type: str = DEFAULT_REPORT_TYPE,
    output: Path | None = None,
) -> str:
    out = output or Path(__file__).resolve().parent / "index.html"
    logger = TokenLogger(f"kr_market_{report_type}")
    market_data = run_pipeline_as_dict()
    pipeline = run_agent_pipeline(market_data, logger=logger)
    opinions = {
        "macro": pipeline["macro"],
        "supply": pipeline["supply"],
        "momentum": pipeline["momentum"],
        "fundamental": pipeline["fundamental"],
        "risk": pipeline["risk"],
        "recommendations": pipeline["recommendations"],
    }
    company_reports = _build_company_reports(report_type, logger)
    report_data = _build_report_data(
        report_type, market_data, opinions, company_reports, pipeline
    )
    path = render_kr_market_page(
        report_data, out, market_data=market_data, pipeline=pipeline
    )
    logger.print_summary()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render kr_market/index.html from pipeline")
    parser.add_argument("--report-type", default=DEFAULT_REPORT_TYPE)
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()
    path = build_index(args.report_type, args.output)
    print(path)


if __name__ == "__main__":
    main()
