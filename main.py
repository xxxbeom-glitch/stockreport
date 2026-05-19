"""Main orchestrator for scheduled stock reports."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from agents import (
    analyze_fundamental,
    analyze_macro,
    analyze_momentum,
    analyze_risk,
    analyze_supply_demand,
)
from data.kr_market import get_stock_snapshot
from data.pipeline import run_pipeline_as_dict
from reports import generate_pdf
from utils.helpers import is_market_holiday
from utils.token_logger import TokenLogger

DEFAULT_REPORT_TYPE = "us_close_kr_before"
TARGET_TIMES: dict[str, tuple[int, int]] = {
    "us_during": (1, 0),
    "us_close_kr_before": (7, 0),
    "kr_during": (13, 0),
    "kr_close_us_before": (17, 0),
}


def _safe_call_with_default(fn_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Call optional integration module safely."""
    module_name = "firebase_client" if fn_name == "save_report" else "slack_sender"
    try:
        module = __import__(module_name, fromlist=[fn_name])
        fn = getattr(module, fn_name)
        result = fn(**payload)
        return {"ok": True, "result": result}
    except ModuleNotFoundError:
        return {"ok": False, "error": f"{module_name}.py not found; skipped."}
    except Exception as exc:
        return {"ok": False, "error": f"{module_name}.{fn_name} failed: {exc}"}


def _build_report_data(report_type: str, market_data: dict[str, Any], opinions: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized report payload for template rendering."""
    now = datetime.now()
    sector_signals = market_data.get("sector_flow", [])
    hot = [s.get("sector", "UNKNOWN") for s in sector_signals if s.get("flow") == "유입"][:5]
    cold = [s.get("sector", "UNKNOWN") for s in sector_signals if s.get("flow") == "유출"][:5]

    discovered = market_data.get("discovered_stocks", [])
    top_themes = [
        {
            "name": "거래량 주도",
            "phase": "진행중",
            "desc": "거래대금이 빠르게 몰린 종목군",
            "etf": "N/A",
            "stocks": [d.get("name", d.get("ticker", "UNKNOWN")) for d in discovered[:5]],
            "volume_leaders": [
                {
                    "name": d.get("name", d.get("ticker", "UNKNOWN")),
                    "ratio": f"{(d.get('volume_ratio') or 0):.2f}x" if d.get("volume_ratio") else "N/A",
                    "change": "N/A",
                    "is_up": True,
                }
                for d in discovered[:5]
            ],
        }
    ]

    stock_analysis = []
    for d in discovered[:5]:
        name = str(d.get("name", d.get("ticker", "UNKNOWN")))
        ticker = str(d.get("ticker", ""))
        market = str(d.get("market", "KOSPI"))
        snapshot = get_stock_snapshot(ticker, market=market) if ticker else {}
        price = snapshot.get("price")
        high_52 = snapshot.get("high_52")
        low_52 = snapshot.get("low_52")
        foreign_net_buy = snapshot.get("foreign_net_buy")
        if foreign_net_buy is None:
            foreign_net_buy = d.get("foreign_net_buy")
        stock_analysis.append(
            {
                "name": name,
                "code": ticker,
                "price": f"{price:,.0f}원" if price else "N/A",
                "high_52": f"{high_52:,.0f}원" if high_52 else "N/A",
                "low_52": f"{low_52:,.0f}원" if low_52 else "N/A",
                "verdict": "홀드",
                "vote_count": "5명 중 5명 보수적",
                "agent_votes": [
                    {"role": "수급", "vote": "홀드", "reason": [opinions["supply"].get("summary", "")]},
                    {"role": "모멘텀", "vote": "홀드", "reason": [opinions["momentum"].get("summary", "")]},
                    {"role": "펀더멘털", "vote": "홀드", "reason": [opinions["fundamental"].get("summary", "")]},
                    {"role": "매크로", "vote": "홀드", "reason": [opinions["macro"].get("summary", "")]},
                    {"role": "리스크", "vote": "홀드", "reason": [opinions["risk"].get("summary", "")]},
                ],
                "metrics": [
                    {"label": "거래량배수", "value": f"{(d.get('volume_ratio') or 0):.2f}x", "sub": "파이프라인 기준"},
                    {
                        "label": "외국인순매수",
                        "value": f"{foreign_net_buy:,.0f}" if foreign_net_buy is not None else "N/A",
                        "sub": "pykrx/KIS",
                    },
                    {"label": "시장", "value": market, "sub": "분류"},
                    {"label": "태그", "value": ", ".join(d.get("source_tags", [])[:2]) or "N/A", "sub": "탐색 출처"},
                ],
                "momentum_tags": [{"text": "관망 우선", "heat": "neu"}],
                "guidance": "추가 재무데이터 확보 전 보수적 접근 권장.",
            }
        )

    return {
        "report_type": report_type,
        "date": now.strftime("%Y-%m-%d"),
        "market_phase": opinions["macro"].get("market_phase", "neutral"),
        "one_line_summary": opinions["risk"].get("summary", "Risk-first interpretation."),
        "indices": market_data.get("indices")
        or {
            "KOSPI": {"value": "N/A", "change": "N/A", "is_up": False},
            "KOSDAQ": {"value": "N/A", "change": "N/A", "is_up": False},
            "NASDAQ": {"value": "N/A", "change": "N/A", "is_up": False},
            "S&P500": {"value": "N/A", "change": "N/A", "is_up": False},
        },
        "indicators": market_data.get("market_indicators") or market_data.get("metadata", {}),
        "sector_flow": {"hot": hot, "cold": cold},
        "top_themes": top_themes,
        "stock_analysis": stock_analysis,
        "action_items": [
            "핵심 섹터만 우선 추적",
            "변동성 큰 종목은 분할 접근",
            "손절 기준 사전 설정",
        ],
        "risk_warning": opinions["risk"].get("do_not", "과도한 레버리지는 지양"),
        "glossary": [
            {"term": "거래량배수", "definition": "오늘 거래량이 평균 대비 몇 배인지"},
            {"term": "손절", "definition": "손실 확대 전 재평가를 위한 기준"},
        ],
    }


def wait_until_send_time(report_type: str) -> None:
    """Wait up to 10 minutes so send aligns to target clock time."""
    target = TARGET_TIMES.get(report_type)
    if not target:
        return
    now = datetime.now()
    hh, mm = target
    target_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    diff = (target_dt - now).total_seconds()
    if 0 < diff <= 600:
        print(f"[INFO] waiting for send time: {int(diff)}s")
        time.sleep(diff)


def run_report(report_type: str = DEFAULT_REPORT_TYPE) -> dict[str, Any]:
    """Run full report pipeline and optional delivery steps."""
    print(f"[INFO] Running report_type={report_type}")
    logger = TokenLogger(report_type)

    if is_market_holiday() and report_type in {"us_close_kr_before", "kr_during", "kr_close_us_before"}:
        print(f"[SKIP] KR holiday/weekend detected for {report_type}")
        return {"report_type": report_type, "skipped": True, "reason": "market_holiday"}

    market_data = run_pipeline_as_dict()

    supply = analyze_supply_demand(market_data, logger=logger)
    momentum = analyze_momentum(market_data, logger=logger)
    fundamental = analyze_fundamental(market_data, logger=logger)
    macro = analyze_macro(
        indicators=market_data.get("market_indicators") or market_data.get("metadata", {}),
        sector_temp={
            item.get("sector", ""): item for item in market_data.get("sector_flow", [])
        },
        news="",
        logger=logger,
    )
    risk = analyze_risk(
        all_opinions={
            "supply": supply,
            "momentum": momentum,
            "fundamental": fundamental,
            "macro": macro,
        },
        market_data=market_data,
        logger=logger,
    )

    opinions = {
        "supply": supply,
        "momentum": momentum,
        "fundamental": fundamental,
        "macro": macro,
        "risk": risk,
    }
    report_data = _build_report_data(report_type, market_data, opinions)
    indices = report_data.get("indices") or {}
    na_indices = [name for name, row in indices.items() if (row or {}).get("value") == "N/A"]
    if na_indices:
        print(f"[WARN] indices contain N/A: {na_indices}")
    else:
        print(f"[INFO] indices populated: {', '.join(indices.keys())}")
    stocks = report_data.get("stock_analysis") or []
    priced = sum(1 for s in stocks if s.get("price") not in (None, "", "N/A"))
    print(f"[INFO] stock snapshots priced: {priced}/{len(stocks)}")

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{datetime.now().strftime('%y%m%d')}_{report_type}.html"
    saved_path = generate_pdf(report_data, str(output_file))

    firebase_result = _safe_call_with_default(
        "save_report",
        {
            "payload": {
                "report_data": report_data,
                "file_path": saved_path,
                "report_type": report_type,
            }
        },
    )
    if not firebase_result["ok"]:
        print(f"[WARN] {firebase_result['error']}")

    pdf_url = ""
    if firebase_result["ok"]:
        firebase_payload = firebase_result.get("result", {})
        if isinstance(firebase_payload, dict):
            pdf_url = str(firebase_payload.get("url", "") or "")

    wait_until_send_time(report_type)
    slack_result = _safe_call_with_default(
        "send_report",
        {
            "payload": {
                "message": f"{report_type} generated: {saved_path}",
                "summary": report_data.get("one_line_summary", ""),
                "report_type": report_type,
                "pdf_url": pdf_url,
            }
        },
    )
    if not slack_result["ok"]:
        print(f"[WARN] {slack_result['error']}")
    logger.print_summary()

    result = {
        "report_type": report_type,
        "saved_path": saved_path,
        "firebase": firebase_result,
        "slack": slack_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    selected_type = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPORT_TYPE
    if selected_type == "weekly":
        try:
            from weekly_report import run_weekly

            run_weekly()
        except Exception as exc:
            print(f"[WARN] weekly execution failed, fallback to run_report: {exc}")
            run_report(selected_type)
    else:
        run_report(selected_type)
