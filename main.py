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
    AGENT_PROFILES,
    analyze_fundamental,
    analyze_macro,
    analyze_momentum,
    analyze_risk,
    analyze_supply_demand,
    generate_company_report,
)
from data.kr_market import get_stock_snapshot, get_top_volume_kr
from data.us_market import get_top_volume_us
from utils.formatters import foreign_net_eok
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
    "us_after": "미장 장후",
    "kr_before": "국장 장전",
    "kr_after": "국장 장후",
    "us_before": "미장 장전",
    "weekly": "위클리 리포트",
}


def _position_52w(price: Any, low: Any, high: Any) -> str:
    try:
        p, lo, hi = float(price), float(low), float(high)
    except (TypeError, ValueError):
        return "N/A"
    if hi <= lo or p <= 0:
        return "N/A"
    pct = (p - lo) / (hi - lo) * 100
    return f"{pct:.0f}%"


def _resolve_agent_vote(opinion: dict[str, Any], name: str, ticker: str) -> tuple[str, list[str]]:
    verdicts = opinion.get("verdicts") or {}
    entry: dict[str, Any] | None = None
    for key in (name, ticker):
        if key in verdicts and isinstance(verdicts[key], dict):
            entry = verdicts[key]
            break
    if entry is None:
        for key, val in verdicts.items():
            if isinstance(val, dict) and (key in name or name in str(key)):
                entry = val
                break
    if entry:
        vote = str(entry.get("vote", "홀드"))
        reasons = entry.get("reason") or [opinion.get("summary", "")]
        if isinstance(reasons, str):
            reasons = [reasons]
        return vote, [str(r) for r in reasons if r][:3]
    summary = str(opinion.get("summary", "")).strip()
    return "홀드", [summary[:200]] if summary else ["의견 없음"]


def _majority_verdict(votes: list[str]) -> str:
    counts: dict[str, int] = {}
    for vote in votes:
        counts[vote] = counts.get(vote, 0) + 1
    for candidate in ("매수", "홀드", "매도"):
        if counts.get(candidate, 0) == max(counts.values(), default=0):
            return candidate
    return "홀드"


def _momentum_tags(volume_ratio: float, change_pct: float) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    if volume_ratio >= 5:
        tags.append({"text": "거래량 폭발", "heat": "hot"})
    elif volume_ratio >= 2:
        tags.append({"text": "거래량 증가", "heat": "warm"})
    if change_pct >= 3:
        tags.append({"text": "강한 상승", "heat": "hot"})
    elif change_pct <= -3:
        tags.append({"text": "약세 압력", "heat": "cold"})
    if not tags:
        tags.append({"text": "관망", "heat": "neu"})
    return tags


def _build_volume_leader(d: dict[str, Any]) -> dict[str, Any]:
    name = str(d.get("name", d.get("ticker", "UNKNOWN")))
    ticker = str(d.get("ticker", ""))
    market = str(d.get("market", "KOSPI"))
    ratio = float(d.get("volume_ratio") or 0.0)
    snapshot = get_stock_snapshot(ticker, market=market) if ticker else {}
    price = snapshot.get("price")
    low_52 = snapshot.get("low_52")
    high_52 = snapshot.get("high_52")
    change_pct = float(snapshot.get("change_rate") or 0.0)
    low_fmt = f"{low_52:,.0f}원" if low_52 else "N/A"
    high_fmt = f"{high_52:,.0f}원" if high_52 else "N/A"
    range_52w = f"{low_fmt} ~ {high_fmt}" if low_52 and high_52 else "N/A"
    return {
        "name": name,
        "ratio": f"{ratio:.2f}x" if ratio else "N/A",
        "price": f"{price:,.0f}원" if price else "N/A",
        "position_52w": _position_52w(price, low_52, high_52),
        "range_52w": range_52w,
        "change": f"{change_pct:+.2f}%",
        "is_up": change_pct >= 0,
    }


def _build_stock_row(d: dict[str, Any], opinions: dict[str, Any]) -> dict[str, Any]:
    name = str(d.get("name", d.get("ticker", "UNKNOWN")))
    ticker = str(d.get("ticker", ""))
    market = str(d.get("market", "KOSPI"))
    ratio = float(d.get("volume_ratio") or 0.0)
    snapshot = get_stock_snapshot(ticker, market=market) if ticker else {}
    price = snapshot.get("price")
    high_52 = snapshot.get("high_52")
    low_52 = snapshot.get("low_52")
    change_pct = float(snapshot.get("change_rate") or 0.0)
    foreign_net_buy = snapshot.get("foreign_net_buy")
    if foreign_net_buy is None:
        foreign_net_buy = d.get("foreign_net_buy")

    agent_votes: list[dict[str, Any]] = []
    vote_labels: list[str] = []
    for profile in AGENT_PROFILES:
        key = profile["key"]
        vote, reasons = _resolve_agent_vote(opinions.get(key, {}), name, ticker)
        vote_labels.append(vote)
        agent_votes.append(
            {
                "name": profile["name"],
                "title": profile["title"],
                "emoji": profile["emoji"],
                "vote": vote,
                "reason": reasons,
            }
        )

    verdict = _majority_verdict(vote_labels)
    buy_n = sum(1 for v in vote_labels if v == "매수")
    sell_n = sum(1 for v in vote_labels if v == "매도")
    hold_n = len(vote_labels) - buy_n - sell_n

    return {
        "name": name,
        "code": ticker,
        "price": f"{price:,.0f}원" if price else "N/A",
        "high_52": f"{high_52:,.0f}원" if high_52 else "N/A",
        "low_52": f"{low_52:,.0f}원" if low_52 else "N/A",
        "position_52w": _position_52w(price, low_52, high_52),
        "verdict": verdict,
        "vote_count": f"매수 {buy_n} · 홀드 {hold_n} · 매도 {sell_n}",
        "foreign_net_eok": foreign_net_eok(foreign_net_buy),
        "agent_votes": agent_votes,
        "metrics": [
            {"label": "거래량배수", "value": f"{ratio:.2f}x" if ratio else "N/A", "sub": "평균 대비"},
            {"label": "외국인순매수", "value": foreign_net_eok(foreign_net_buy), "sub": "당일 추정"},
            {"label": "시장", "value": market, "sub": "분류"},
            {"label": "등락률", "value": f"{change_pct:+.2f}%", "sub": "전일 대비"},
        ],
        "momentum_tags": _momentum_tags(ratio, change_pct),
        "guidance": opinions["risk"].get("do_not", "과도한 추격매수는 지양"),
    }


def _build_company_reports(report_type: str, logger: TokenLogger) -> list[dict[str, Any]]:
    """Build Gemini company briefs for scheduled hot-volume reports."""
    rows: list[dict[str, Any]] = []
    if report_type == "us_close_kr_before":
        leaders = get_top_volume_us(5)
        market_label = "US"
    elif report_type == "kr_during":
        leaders = get_top_volume_kr(5, market="KOSPI")
        market_label = "KR"
    else:
        return rows

    for item in leaders:
        ticker = str(item.get("ticker", ""))
        name = str(item.get("name", ticker))
        market = str(item.get("market", market_label))
        if market.upper() in {"US", "NASDAQ", "NYSE"}:
            market = "US"
        else:
            market = "KOSPI"
        snapshot: dict[str, Any] = {}
        if market != "US" and ticker:
            snapshot = get_stock_snapshot(ticker, market=market)
        price = item.get("price_fmt") or item.get("price")
        if market != "US" and snapshot.get("price"):
            price = f"{snapshot['price']:,.0f}원"
        elif isinstance(price, (int, float)):
            price = f"${price:,.2f}" if market == "US" else f"{price:,.0f}원"

        report = generate_company_report(
            ticker=ticker,
            name=name,
            market=market,
            logger=logger,
            extra={**item, **(snapshot or {})},
        )
        low = snapshot.get("low_52") if snapshot else item.get("low_52")
        high = snapshot.get("high_52") if snapshot else item.get("high_52")
        if market == "US":
            range_52w = "N/A"
        else:
            range_52w = (
                f"{low:,.0f}원 ~ {high:,.0f}원"
                if low and high
                else _position_52w(snapshot.get("price"), low, high)
            )
        rows.append(
            {
                **report,
                "price_display": price or "N/A",
                "volume_ratio": f"{(item.get('volume_ratio') or 0):.2f}x",
                "range_52w": range_52w,
                "change": item.get("change", "N/A"),
                "is_up": item.get("is_up", True),
            }
        )
    return rows


def _build_report_data(
    report_type: str,
    market_data: dict[str, Any],
    opinions: dict[str, Any],
    company_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a normalized report payload for template rendering."""
    now = datetime.now()
    sector_signals = market_data.get("sector_flow", [])
    hot = [s.get("sector", "UNKNOWN") for s in sector_signals if s.get("flow") == "유입"][:5]
    cold = [s.get("sector", "UNKNOWN") for s in sector_signals if s.get("flow") == "유출"][:5]

    discovered = market_data.get("discovered_stocks", [])
    volume_leaders = [_build_volume_leader(d) for d in discovered[:5]]
    top_themes = [
        {
            "name": "거래량 주도",
            "phase": "진행중",
            "desc": "거래대금이 빠르게 몰린 종목군",
            "etf": "N/A",
            "stocks": [d.get("name", d.get("ticker", "UNKNOWN")) for d in discovered[:5]],
            "volume_leaders": volume_leaders,
        }
    ]

    stock_analysis = [_build_stock_row(d, opinions) for d in discovered[:5]]

    return {
        "report_type": report_type,
        "report_type_label": REPORT_TYPE_LABELS.get(report_type, report_type),
        "report_title": f"Stock Report · {REPORT_TYPE_LABELS.get(report_type, report_type)}",
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
        "indicators": market_data.get("market_indicators") or {},
        "indicator_labels": INDICATOR_LABELS,
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
            {"term": "외국인순매수", "definition": "외국인 투자자의 순매수 금액 (억원 단위)"},
        ],
        "company_reports": company_reports or [],
        "has_company_reports": bool(company_reports),
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
    company_reports = _build_company_reports(report_type, logger)
    if company_reports:
        print(f"[INFO] company_reports: {len(company_reports)}")
    report_data = _build_report_data(report_type, market_data, opinions, company_reports)
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
