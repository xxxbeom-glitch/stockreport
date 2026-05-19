# -*- coding: utf-8 -*-
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

root = Path(__file__).resolve().parents[1]
t = (root / "reports/templates/_report_core.html").read_text(encoding="utf-8")
idx = t.find("stock.verdict ==")
print("snippet:", repr(t[idx : idx + 45]))
print("has 매수 literal:", "매수" in t)

env = Environment(loader=FileSystemLoader(str(root / "reports/templates")))
html = env.get_template("03_kr_during.html").render(
    report_type="kr_during",
    report_type_label="국장",
    date="2026-05-19",
    header_date="2026-05-19",
    market_phase="neutral",
    one_line_summary="요약",
    indices={
        "KOSPI": {"value": "1", "change": "+1%", "is_up": True},
        "KOSDAQ": {"value": "1", "change": "-1%", "is_up": False},
    },
    indicators={},
    indicator_labels={"vix": "VIX"},
    sector_flow={"hot": [], "cold": []},
    top_themes=[],
    stock_analysis=[
        {
            "name": "A",
            "code": "1",
            "price": "1",
            "change": "+1%",
            "is_up": True,
            "low_52": "1",
            "high_52": "2",
            "range_52w": "1~2",
            "foreign_net_eok": "1",
            "verdict": "매수",
            "vote_count": "1",
            "agent_votes": [
                {"emoji": "x", "name": "J", "title": "t", "vote": "매수", "reason": ["r"]}
            ],
        }
    ],
    risk_warning="w",
    action_items=["a"],
    glossary=[],
    has_company_reports=False,
)
print("verdict-badge buy:", "verdict-badge buy" in html)
print("vote-buy:", "vote-buy" in html)
Path(root / "outputs/_verify_design.html").write_text(html, encoding="utf-8")
print("wrote outputs/_verify_design.html")
