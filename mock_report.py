"""Generate a mock HTML report without market/API calls, then upload and notify.

Used by `.github/workflows/test_html.yml` to validate template design end-to-end.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from agents.profiles import AGENT_PROFILES
from firebase_client import save_report
from reports import generate_pdf
from slack_sender import send_report

INDICATOR_LABELS: dict[str, str] = {
    "dollar_index": "달러인덱스",
    "us10y": "미국10년금리",
    "vix": "VIX",
    "wti": "WTI",
    "copper": "구리",
}

REPORT_TYPE_LABELS: dict[str, str] = {
    "us_during": "미장 장중",
    "us_close_kr_before": "국장 장전",
    "kr_during": "국장 장중",
    "kr_close_us_before": "국장 장후",
    "kr_before": "국장 장전",
    "kr_after": "국장 장후",
}

DEFAULT_REPORT_TYPE = "kr_during"


def _mock_agent_votes(
    votes: tuple[str, ...] = ("매수", "매수", "홀드", "홀드", "매도"),
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reasons = {
        "매수": ["수급 개선이 확인됩니다.", "단기 모멘텀이 유효합니다."],
        "홀드": ["추가 확인이 필요합니다.", "밸류에이션 부담이 있습니다."],
        "매도": ["변동성 리스크가 큽니다.", "리스크 대비 보상이 낮습니다."],
    }
    for profile, vote in zip(AGENT_PROFILES, votes, strict=False):
        rows.append(
            {
                "name": profile["name"],
                "title": profile["title"],
                "emoji": profile["emoji"],
                "vote": vote,
                "reason": reasons.get(vote, ["의견 없음"]),
            }
        )
    return rows


def _mock_volume_leader(
    rank: int,
    name: str,
    ticker: str,
    ratio: str,
    price: str,
    change: str,
    is_up: bool,
    range_52w: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "ticker": ticker,
        "ratio": ratio,
        "price": price,
        "change": change,
        "is_up": is_up,
        "range_52w": range_52w,
        "position_52w": "62%",
        "position_pct": 62,
    }


def _mock_stock(
    name: str,
    code: str,
    price: str,
    change: str,
    is_up: bool,
    low_52: str,
    high_52: str,
    foreign_net_eok: str,
    verdict: str,
    votes: tuple[str, ...],
) -> dict[str, Any]:
    vote_labels = list(votes)
    buy_n = sum(1 for v in vote_labels if v == "매수")
    sell_n = sum(1 for v in vote_labels if v == "매도")
    hold_n = len(vote_labels) - buy_n - sell_n
    return {
        "name": name,
        "code": code,
        "price": price,
        "change": change,
        "is_up": is_up,
        "low_52": low_52,
        "high_52": high_52,
        "range_52w": f"{low_52} ~ {high_52}",
        "position_52w": "62%",
        "position_pct": 62,
        "foreign_net_eok": foreign_net_eok,
        "verdict": verdict,
        "vote_count": f"매수 {buy_n} · 홀드 {hold_n} · 매도 {sell_n}",
        "agent_votes": _mock_agent_votes(votes),
    }


def _mock_company(
    name: str,
    ticker: str,
    one_liner: str,
    why_hot: str,
    verdict: str,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": name,
        "market": "KOSPI",
        "one_liner": one_liner,
        "why_hot": why_hot,
        "business": "핵심 사업은 반도체·전장 부품이며, 대형 고객사와 장기 공급 계약을 보유하고 있습니다.",
        "strength": "현금흐름과 기술 경쟁력이 양호합니다.",
        "risk": "업황 둔화 시 실적 변동성이 커질 수 있습니다.",
        "verdict": verdict,
        "target_comment": "단기 모멘텀은 유효하나, 분할 접근을 권장합니다.",
        "price_display": "72,000원",
        "volume_ratio": "4.20x",
    }


def build_mock_report_data(report_type: str = DEFAULT_REPORT_TYPE) -> dict[str, Any]:
    """Build template-ready payload without external APIs."""
    now = datetime.now()
    leaders = [
        _mock_volume_leader(1, "삼성전자", "005930", "4.20x", "72,000원", "+2.10%", True, "55,000원 ~ 80,000원"),
        _mock_volume_leader(2, "SK하이닉스", "000660", "3.10x", "180,000원", "+1.50%", True, "120,000원 ~ 200,000원"),
        _mock_volume_leader(3, "한화에어로스페이스", "012450", "2.80x", "890,000원", "+0.85%", True, "700,000원 ~ 950,000원"),
        _mock_volume_leader(4, "현대차", "005380", "2.10x", "245,000원", "-0.40%", False, "200,000원 ~ 280,000원"),
        _mock_volume_leader(5, "LG에너지솔루션", "373220", "1.95x", "380,000원", "+0.25%", True, "320,000원 ~ 420,000원"),
    ]

    stocks = [
        _mock_stock(
            "삼성전자",
            "005930",
            "72,000원",
            "+2.10%",
            True,
            "55,000원",
            "80,000원",
            "1,240억원",
            "매수",
            ("매수", "매수", "홀드", "홀드", "매도"),
        ),
        _mock_stock(
            "SK하이닉스",
            "000660",
            "180,000원",
            "+1.50%",
            True,
            "120,000원",
            "200,000원",
            "890억원",
            "매수",
            ("매수", "매수", "매수", "홀드", "홀드"),
        ),
    ]

    company_reports: list[dict[str, Any]] = []
    if report_type in {"kr_during", "us_close_kr_before"}:
        company_reports = [
            _mock_company(
                "삼성전자",
                "005930",
                "AI 수요 수혜 대형주",
                "거래량이 평소 대비 4배 급증하며 외국인 순매수가 동반되었습니다.",
                "매수",
            ),
            _mock_company(
                "SK하이닉스",
                "000660",
                "HBM 모멘텀 지속",
                "실적 시즌 앞두고 메모리 업황 기대감이 거래량을 끌어올렸습니다.",
                "홀드",
            ),
        ]

    return {
        "report_type": report_type,
        "report_type_label": REPORT_TYPE_LABELS.get(report_type, report_type),
        "report_title": f"[MOCK] Stock Report · {REPORT_TYPE_LABELS.get(report_type, report_type)}",
        "date": now.strftime("%Y-%m-%d"),
        "market_phase": "neutral",
        "one_line_summary": "[테스트] 변동성 확대 구간 — 핵심 섹터 위주로 선별 접근하세요.",
        "indices": {
            "KOSPI": {"value": "2,612.45", "change": "+1.02%", "is_up": True},
            "KOSDAQ": {"value": "801.32", "change": "-0.48%", "is_up": False},
            "S&P500": {"value": "5,218.40", "change": "+0.21%", "is_up": True},
            "NASDAQ": {"value": "16,274.90", "change": "+0.35%", "is_up": True},
            "DOW": {"value": "39,127.80", "change": "+0.10%", "is_up": True},
            "RUSSELL2000": {"value": "2,098.50", "change": "-0.15%", "is_up": False},
        },
        "indicators": {
            "dollar_index": {"value": "104.25", "change": "+0.12%", "is_up": True},
            "us10y": {"value": "4.25%", "change": "+0.02", "is_up": True},
            "vix": {"value": "15.20", "change": "-2.10%", "is_up": False},
            "wti": {"value": "72.40", "change": "+0.55%", "is_up": True},
            "copper": {"value": "4.12", "change": "-0.20%", "is_up": False},
        },
        "indicator_labels": INDICATOR_LABELS,
        "sector_flow": {
            "hot": ["반도체", "AI", "방산"],
            "cold": ["에너지", "유틸리티"],
        },
        "top_themes": [
            {
                "name": "거래량 주도",
                "phase": "진행중",
                "desc": "거래대금이 빠르게 몰린 종목군 (목 데이터)",
                "volume_leaders": leaders,
            }
        ],
        "stock_analysis": stocks,
        "action_items": [
            "핵심 섹터만 우선 추적",
            "변동성 큰 종목은 분할 접근",
            "손절 기준을 사전에 설정",
        ],
        "risk_warning": "[테스트] 급등주 추격매수는 자제하고, 손절 기준을 먼저 정하세요.",
        "glossary": [
            {"term": "거래량배수", "definition": "오늘 거래량이 평균 대비 몇 배인지"},
            {"term": "손절", "definition": "손실 확대 전 재평가를 위한 기준"},
            {"term": "외국인순매수", "definition": "외국인 투자자의 순매수 금액 (억원 단위)"},
        ],
        "company_reports": company_reports,
        "has_company_reports": bool(company_reports),
        "meta": {"mode": "mock", "generated_at": now.isoformat()},
    }


def _is_configured(env_name: str) -> bool:
    return bool(os.getenv(env_name, "").strip())


def _log_json(label: str, data: dict[str, Any]) -> None:
    """Print JSON safely on Windows consoles (cp949)."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    try:
        print(f"{label}: {text}")
    except UnicodeEncodeError:
        print(f"{label}: {json.dumps(data, ensure_ascii=True, default=str)}")


def run_mock_report(report_type: str | None = None) -> dict[str, Any]:
    """Render mock HTML, upload to Firebase, and notify Slack."""
    selected = report_type or os.getenv("MOCK_REPORT_TYPE", DEFAULT_REPORT_TYPE)
    print(f"[INFO] mock_report type={selected}")

    report_data = build_mock_report_data(selected)
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"mock_{datetime.now().strftime('%y%m%d')}_{selected}.html"

    saved_path = generate_pdf(report_data, str(output_file))
    html_size = Path(saved_path).stat().st_size
    print(f"[INFO] HTML saved: {saved_path} ({html_size:,} bytes)")
    if html_size < 2000:
        raise RuntimeError(f"HTML output too small ({html_size} bytes) — template may have failed")

    # CI provides FIREBASE_SERVICE_ACCOUNT; local dev may use FIREBASE_KEY_PATH file.
    firebase_configured = _is_configured("FIREBASE_SERVICE_ACCOUNT")
    slack_configured = os.getenv("STOCKREPORT_MOCK_SLACK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ) and _is_configured("SLACK_BOT_TOKEN")

    firebase_result = save_report(
        payload={
            "report_data": report_data,
            "file_path": saved_path,
            "report_type": selected,
        }
    )
    _log_json("[INFO] firebase", firebase_result)

    pdf_url = str(firebase_result.get("url") or "")
    report_data["pdf_url"] = pdf_url
    if slack_configured:
        slack_result = send_report(
            payload={
                "report_data": report_data,
                "message": f"[MOCK] {selected} HTML design test",
                "summary": report_data.get("one_line_summary", ""),
                "report_type": selected,
                "pdf_url": pdf_url,
            }
        )
    else:
        slack_result = {"ok": True, "skipped": True, "reason": "mock_slack_disabled"}
    _log_json("[INFO] slack", slack_result)

    ok = True
    if firebase_configured and not firebase_result.get("url"):
        print("[WARN] Firebase configured but no public URL returned (upload may have failed)")
        ok = False
    if slack_configured and not slack_result.get("ok"):
        print("[ERROR] Slack send failed")
        ok = False

    result = {
        "report_type": selected,
        "saved_path": saved_path,
        "html_bytes": html_size,
        "firebase": firebase_result,
        "slack": slack_result,
    }
    if not ok:
        sys.exit(1)
    return result


if __name__ == "__main__":
    arg_type = sys.argv[1] if len(sys.argv) > 1 else None
    outcome = run_mock_report(arg_type)
    _log_json("[DONE]", outcome)
