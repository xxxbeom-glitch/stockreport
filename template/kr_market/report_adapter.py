"""Map pipeline / report_data → kr_market Jinja context (06_CURSOR_IMPLEMENTATION_TASK)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.label_rules import VALID_LABELS, normalize_label
from agents.label_vote_helpers import normalize_ticker
from data.kr_market import get_kis_sector_trading_value, get_sector_top_stocks
from data.kr_watchlist import (
    build_watchlist_stock_pool,
    sort_kr_focus_stocks,
    stock_filter_options,
    watchlist_sectors_meta,
)
from data.sources import fetch_yfinance_history
from data.us_market import _fetch_usd_krw
from utils.ui_comment import format_ui_comment

NA = "N/A"
AI_COMMENT_FALLBACK = "시장·섹터 데이터 기준 코멘트 생성 중."
COMPANY_SUMMARY_FALLBACK = "기업 개요 데이터 수집 중."


def _is_offline_render() -> bool:
    """CI/검증: KIS·KRX·yfinance 호출 생략."""
    return os.getenv("KR_MARKET_OFFLINE", "").strip().lower() in ("1", "true", "yes")

KR_INDEX_SPECS: tuple[tuple[str, str], ...] = (
    ("코스피", "KOSPI"),
    ("코스닥", "KOSDAQ"),
    ("달러/원 환율", "USDKRW"),
)


def _safe_str(value: Any) -> str:
    if value is None or str(value).strip() in {"", "None", "null"}:
        return NA
    return str(value).strip()


def _index_row(label: str, value: Any, change: Any, is_up: bool | None = None) -> dict[str, Any]:
    chg_s = _safe_str(change)
    if chg_s == NA:
        up = False
    elif is_up is not None:
        up = is_up
    else:
        up = chg_s.startswith("+")
    val_s = _safe_str(value)
    if val_s != NA and label != "달러/원 환율" and not val_s.endswith("원") and label in ("코스피", "코스닥"):
        try:
            val_s = f"{float(str(value).replace(',', '')):,.2f}"
        except (TypeError, ValueError):
            pass
    return {"label": label, "value": val_s, "change": chg_s, "is_up": up}


def _build_indices(indices: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """KR template rows: KOSPI, KOSDAQ, USD/KRW."""
    meta: dict[str, str] = {}
    rows: list[dict[str, Any]] = []

    for label, key in KR_INDEX_SPECS:
        if key == "USDKRW":
            rate, chg, up, src = _usd_krw_snapshot()
            rows.append(_index_row(label, rate, chg, up))
            meta["USDKRW"] = src
            continue
        row = indices.get(key) or {}
        val = row.get("value", NA)
        chg = row.get("change", NA)
        up = row.get("is_up")
        rows.append(_index_row(label, val, chg, up if isinstance(up, bool) else None))
        meta[key] = "live" if _safe_str(val) != NA else "fallback"

    return rows, meta


def _usd_krw_snapshot() -> tuple[str, str, bool, str]:
    if _is_offline_render():
        return (NA, NA, False, "offline")
    hist = fetch_yfinance_history("USDKRW=X", period="5d")
    if hist is not None and len(hist) >= 1:
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
        chg_pct = ((last - prev) / prev * 100.0) if prev else 0.0
        return (
            f"{last:,.2f}",
            f"{chg_pct:+.2f}%",
            chg_pct >= 0,
            "live",
        )
    rate = _fetch_usd_krw()
    if rate and rate > 0:
        return (f"{rate:,.2f}", NA, True, "fallback_rate")
    return (NA, NA, False, "fallback")


def _sector_change_map() -> dict[str, float]:
    out: dict[str, float] = {}
    for row in get_kis_sector_trading_value() or []:
        name = str(row.get("name", "")).strip()
        if name:
            out[name] = float(row.get("change_rate") or 0.0)
    return out


def _sector_flow_label(name: str, is_inflow: bool, chg_map: dict[str, float]) -> str:
    chg = chg_map.get(name)
    if chg is not None:
        sign = "+" if chg > 0 else ""
        return f"{sign}{chg:.2f}%"
    return NA


def _sector_commentary(
    name: str,
    *,
    is_inflow: bool,
    stock_names: list[str],
    pipeline: dict[str, Any] | None,
    pulse: str,
) -> tuple[str, str]:
    """Return (comment, source): ai | rules | fallback."""
    stocks_bit = ", ".join(stock_names[:3]) if stock_names else ""
    if is_inflow and stocks_bit:
        rules = f"{name} 유입. {stocks_bit} 거래 집중."
        return rules, "rules"
    if not is_inflow and stocks_bit:
        return f"{name} 유출. {stocks_bit} 약세 동반.", "rules"
    if pulse:
        return format_ui_comment(pulse), "ai"
    kr_ui = (pipeline or {}).get("kr_ui") or {}
    if kr_ui.get("pulse_summary"):
        return format_ui_comment(str(kr_ui["pulse_summary"])), "ai"
    return AI_COMMENT_FALLBACK, "fallback"


def _build_sectors(
    report_data: dict[str, Any],
    pipeline: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    sector_flow = report_data.get("sector_flow") or {}
    hot = list(sector_flow.get("hot") or [])[:6]
    cold = list(sector_flow.get("cold") or [])[:6]
    if _is_offline_render():
        chg_map: dict[str, float] = {}
        top_stocks: dict[str, list] = {}
    else:
        chg_map = _sector_change_map()
        top_stocks = get_sector_top_stocks(3) or {}
    pulse = str(((pipeline or {}).get("engines") or {}).get("market_pulse", {}).get("pulse_summary", ""))

    cards: list[dict[str, Any]] = []
    meta: dict[str, str] = {}
    used_pulse = False

    for name in hot:
        names = [r.get("name", "") for r in top_stocks.get(name, []) if r.get("name")]
        comment, src = _sector_commentary(
            name, is_inflow=True, stock_names=names, pipeline=pipeline, pulse="" if used_pulse else pulse
        )
        used_pulse = used_pulse or bool(pulse)
        cards.append(
            {
                "name": name,
                "sector_key": name,
                "is_inflow": True,
                "flow_amount": _sector_flow_label(name, True, chg_map),
                "tag": "주요 상승 종목" if names else NA,
                "stock_names": names,
                "commentary": comment,
                "commentary_source": src,
            }
        )
        meta[name] = src

    for name in cold:
        names = [r.get("name", "") for r in top_stocks.get(name, []) if r.get("name")]
        comment, src = _sector_commentary(name, is_inflow=False, stock_names=names, pipeline=pipeline, pulse="")
        cards.append(
            {
                "name": name,
                "sector_key": name,
                "is_inflow": False,
                "flow_amount": _sector_flow_label(name, False, chg_map),
                "tag": "주요 종목" if names else NA,
                "stock_names": names,
                "commentary": comment,
                "commentary_source": src,
            }
        )
        meta[name] = src

    if not cards:
        cards.append(
            {
                "name": "섹터 데이터",
                "sector_key": "전체섹터",
                "is_inflow": True,
                "flow_amount": NA,
                "tag": NA,
                "stock_names": [],
                "commentary": AI_COMMENT_FALLBACK,
                "commentary_source": "fallback",
            }
        )

    filter_opts = ["전체섹터"] + [c["sector_key"] for c in cards if c["sector_key"] != "전체섹터"]
    return cards, filter_opts, meta


def _company_map(company_reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in company_reports or []:
        ticker = normalize_ticker(str(row.get("ticker", "")))
        if ticker:
            out[ticker] = row
    return out


def _company_summary_text(row: dict[str, Any] | None, *, pipeline: dict[str, Any] | None, ticker: str) -> tuple[str, str]:
    if not row:
        return COMPANY_SUMMARY_FALLBACK, "fallback"
    parts = [
        str(row.get("one_liner") or row.get("business") or "").strip(),
        str(row.get("why_hot") or row.get("strength") or "").strip(),
    ]
    parts = [p for p in parts if p and p != NA]
    if parts:
        return format_ui_comment("\n".join(parts[:2])), "ai"
    return COMPANY_SUMMARY_FALLBACK, "fallback"


def _map_stock(
    row: dict[str, Any],
    *,
    company_by_ticker: dict[str, dict[str, Any]],
    pipeline: dict[str, Any] | None,
) -> dict[str, Any]:
    ticker = str(row.get("code") or row.get("ticker") or "")
    key = normalize_ticker(ticker)
    label = row.get("label") or row.get("verdict") or NA
    reason = row.get("label_reason") or ""
    if not reason and row.get("label_reason_lines"):
        reason = "\n".join(row["label_reason_lines"])
    reason = format_ui_comment(reason) if reason else AI_COMMENT_FALLBACK

    company_text, company_src = _company_summary_text(company_by_ticker.get(key), pipeline=pipeline, ticker=key)
    if not company_text or company_text == COMPANY_SUMMARY_FALLBACK:
        inline = str(row.get("company_summary") or "").strip()
        if inline and inline != NA:
            company_text = format_ui_comment(inline)
            company_src = "ai"

    sector_key = str(row.get("sector_key") or "")
    sector_name = str(row.get("sector_name") or row.get("theme") or NA)
    target_price = row.get("target_price")

    metrics = [
        {"label": "현재가", "value": _safe_str(row.get("price"))},
        {"label": "목표가", "value": _safe_str(target_price)},
        {"label": "외국인 순매수", "value": _safe_str(row.get("foreign_net_eok"))},
        {"label": "52주 최고가", "value": _safe_str(row.get("high_52"))},
    ]

    return {
        "name": row.get("name", NA),
        "ticker": ticker or NA,
        "sector_key": sector_key or NA,
        "sector_name": sector_name,
        "verdict_badge": label if label in VALID_LABELS else NA,
        "verdict_class": row.get("verdict_class", "hold"),
        "opinion": reason,
        "opinion_source": "ai" if reason != AI_COMMENT_FALLBACK else "fallback",
        "metrics": metrics,
        "company_summary": company_text,
        "company_summary_source": company_src,
        "logo_url": row.get("logo_url"),
        "sector_order": row.get("sector_order"),
        "stock_order": row.get("stock_order"),
    }


def build_report_data_js(
    ctx: dict[str, Any],
    *,
    report_data: dict[str, Any] | None = None,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Frontend/debug payload (window.reportData). UI still uses Jinja SSR."""
    rd = report_data or {}
    market_meta = ctx.get("market_meta") or {}
    indices_map: dict[str, Any] = {}
    for row in ctx.get("indices") or []:
        label = str(row.get("label", ""))
        if label:
            indices_map[label] = {
                "value": row.get("value", NA),
                "change": row.get("change", NA),
                "is_up": row.get("is_up"),
            }

    sectors_map: dict[str, Any] = {}
    for card in ctx.get("sectors") or []:
        key = str(card.get("sector_key") or card.get("name") or "")
        if key:
            sectors_map[key] = {
                "name": card.get("name", NA),
                "is_inflow": card.get("is_inflow"),
                "flow_amount": card.get("flow_amount", NA),
                "commentary": card.get("commentary", NA),
                "commentary_source": card.get("commentary_source", NA),
                "stock_names": card.get("stock_names") or [],
            }

    watchlist_stocks_out: list[dict[str, Any]] = []
    stocks_out: list[dict[str, Any]] = []
    ai_votes_out: list[dict[str, Any]] = []
    for row in rd.get("stock_analysis") or []:
        ticker = str(row.get("code") or row.get("ticker") or "")
        label = normalize_label(row.get("label") or row.get("verdict"))
        reason = row.get("label_reason") or ""
        memo = str(row.get("company_summary") or "").strip() or COMPANY_SUMMARY_FALLBACK
        wl_row = {
            "sector_key": row.get("sector_key") or NA,
            "sector_name": row.get("sector_name") or row.get("theme", NA),
            "ticker": ticker or NA,
            "name": row.get("name", NA),
            "label": label,
            "reason": reason or NA,
            "current_price": row.get("price", NA),
            "target_price": row.get("target_price", NA),
            "foreign_net_buy": row.get("foreign_net_eok", NA),
            "high_52w": row.get("high_52", NA),
            "memo": memo,
            "verdict_class": row.get("verdict_class", NA),
        }
        watchlist_stocks_out.append(wl_row)
        stocks_out.append(
            {
                "ticker": ticker or NA,
                "name": row.get("name", NA),
                "sector_key": row.get("sector_key") or row.get("theme", NA),
                "label": label,
                "reason": reason or NA,
                "verdict_class": row.get("verdict_class", NA),
            }
        )
        for v in row.get("ai_votes") or []:
            if not isinstance(v, dict):
                continue
            ai_votes_out.append(
                {
                    "ticker": ticker or NA,
                    "model": v.get("model", NA),
                    "engine": v.get("engine", NA),
                    "label": normalize_label(v.get("label")),
                    "reason": v.get("reason", NA),
                    "confidence": v.get("confidence", 0),
                    "source": v.get("source", NA),
                }
            )

    if not watchlist_stocks_out:
        for s in ctx.get("stocks") or []:
            label = normalize_label(s.get("verdict_badge"))
            wl_row = {
                "sector_key": s.get("sector_key", NA),
                "sector_name": s.get("sector_name", NA),
                "ticker": s.get("ticker", NA),
                "name": s.get("name", NA),
                "label": label,
                "reason": s.get("opinion", NA),
                "current_price": NA,
                "target_price": NA,
                "foreign_net_buy": NA,
                "high_52w": NA,
                "memo": s.get("company_summary", COMPANY_SUMMARY_FALLBACK),
                "verdict_class": s.get("verdict_class", NA),
            }
            watchlist_stocks_out.append(wl_row)
            stocks_out.append(
                {
                    "ticker": s.get("ticker", NA),
                    "name": s.get("name", NA),
                    "sector_key": s.get("sector_key", NA),
                    "label": label,
                    "reason": s.get("opinion", NA),
                    "verdict_class": s.get("verdict_class", NA),
                }
            )

    meta = ctx.get("_meta") or {}
    return {
        "market": {
            "type": "KR",
            "meta": market_meta,
            "commentary": ctx.get("market_commentary", NA),
            "commentary_source": ctx.get("market_commentary_source", NA),
            "indices": indices_map,
        },
        "sectors": sectors_map,
        "stocks": stocks_out,
        "watchlistStocks": watchlist_stocks_out,
        "aiVotes": ai_votes_out,
        "meta": {
            "market_type": "KR",
            "labels": list(VALID_LABELS),
            "watchlistSectors": watchlist_sectors_meta(),
            "generated_at": meta.get("generated_at", NA),
            "indices": meta.get("indices", {}),
            "sectors": meta.get("sectors", {}),
            "pipeline_engines": list(((pipeline or {}).get("engines") or {}).keys()),
        },
    }


def _market_commentary(report_data: dict[str, Any], pipeline: dict[str, Any] | None) -> tuple[str, str]:
    kr_ui = (pipeline or {}).get("kr_ui") or {}
    if kr_ui.get("market_comment"):
        return format_ui_comment(str(kr_ui["market_comment"])), "ai"
    reason = report_data.get("market_phase_reason") or ""
    if reason:
        return format_ui_comment(str(reason)), "ai"
    summary = (pipeline or {}).get("risk", {}).get("one_line_summary") or report_data.get("one_line_summary")
    if summary and summary != NA:
        return format_ui_comment(str(summary)), "ai"
    return AI_COMMENT_FALLBACK, "fallback"


def _weekday_ko(dt: datetime) -> str:
    names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    return names[dt.weekday()]


def build_static_preview_report_data() -> dict[str, Any]:
    """Offline sample: watchlist subset, N/A metrics, 2-label examples only."""
    from agents.label_rules import LABEL_REGRET, LABEL_TIMING

    samples: list[dict[str, Any]] = [
        {
            "name": "솔브레인",
            "code": "036830",
            "sector_key": "semiconductor_materials",
            "sector_name": "반도체 소재",
            "sector_order": 0,
            "stock_order": 0,
            "label": LABEL_REGRET,
            "label_reason": "유입 섹터 내 수급 개선.\n실적 확인 전제.",
            "verdict_class": "buy",
            "price": "N/A",
            "target_price": "N/A",
            "foreign_net_eok": "N/A",
            "high_52": "N/A",
            "company_summary": "반도체 소재·세정 케미칼.\n단기 테마 수급은 유효.",
        },
        {
            "name": "리노공업",
            "code": "058470",
            "sector_key": "semiconductor_parts",
            "sector_name": "반도체 부품",
            "sector_order": 1,
            "stock_order": 0,
            "label": LABEL_REGRET,
            "label_reason": "외국인 순매수와 거래량 동반.\n52주 상단은 부담.",
            "verdict_class": "buy",
            "price": "72,000원",
            "target_price": "N/A",
            "foreign_net_eok": "+120억",
            "high_52": "75,000원",
            "company_summary": "테스트·소켓 부품.\n단기 수급 재료는 유효.",
        },
        {
            "name": "한미반도체",
            "code": "042700",
            "sector_key": "semiconductor_equipment",
            "sector_name": "반도체 장비",
            "sector_order": 2,
            "stock_order": 0,
            "label": LABEL_TIMING,
            "label_reason": "단기 과열 구간.\n고점 부담이 큼.",
            "verdict_class": "sell",
            "price": "N/A",
            "target_price": "N/A",
            "foreign_net_eok": "N/A",
            "high_52": "N/A",
            "company_summary": "",
        },
        {
            "name": "한화에어로스페이스",
            "code": "012450",
            "sector_key": "defense_space",
            "sector_name": "방산·우주",
            "sector_order": 3,
            "stock_order": 0,
            "label": LABEL_REGRET,
            "label_reason": "방산 수주 모멘텀.\n변동성은 존재.",
            "verdict_class": "buy",
            "price": "N/A",
            "target_price": "N/A",
            "foreign_net_eok": "N/A",
            "high_52": "N/A",
            "company_summary": "",
        },
        {
            "name": "HD현대중공업",
            "code": "329180",
            "sector_key": "shipbuilding_marine_shipping",
            "sector_name": "조선·해양방산·해운",
            "sector_order": 4,
            "stock_order": 1,
            "label": LABEL_TIMING,
            "label_reason": "조선 사이클 부담.\n단기 조정 가능.",
            "verdict_class": "sell",
            "price": "N/A",
            "target_price": "N/A",
            "foreign_net_eok": "N/A",
            "high_52": "N/A",
            "company_summary": "",
        },
        {
            "name": "HMM",
            "code": "011200",
            "sector_key": "shipbuilding_marine_shipping",
            "sector_name": "조선·해양방산·해운",
            "sector_order": 4,
            "stock_order": 5,
            "label": LABEL_TIMING,
            "label_reason": "운임 둔화 신호.\n진입 타이밍 부담.",
            "verdict_class": "sell",
            "price": "N/A",
            "target_price": "N/A",
            "foreign_net_eok": "N/A",
            "high_52": "N/A",
            "company_summary": "",
        },
    ]
    return {
        "report_type": "us_close_kr_before",
        "indices": {
            "KOSPI": {"value": "2,650.00", "change": "+0.42%", "is_up": True},
            "KOSDAQ": {"value": "850.12", "change": "-0.15%", "is_up": False},
        },
        "market_phase_reason": "코스피 소폭 상승.\n외국인 순매수는 제한적.",
        "sector_flow": {
            "hot": ["반도체 소재", "반도체 장비"],
            "cold": ["조선·해양방산·해운"],
        },
        "stock_analysis": sort_kr_focus_stocks(samples),
    }


def build_kr_market_context(
    report_data: dict[str, Any],
    *,
    market_data: dict[str, Any] | None = None,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build Jinja context for template/kr_market (marketType=KR only).
    Numeric fields use N/A when missing; commentary fields tagged by source.
    """
    del market_data  # reserved for US extension
    now = datetime.now()
    indices_raw = report_data.get("indices") or {}
    index_rows, index_meta = _build_indices(indices_raw)
    market_comment, market_comment_src = _market_commentary(report_data, pipeline)
    sectors, sector_filters, sector_meta = _build_sectors(report_data, pipeline)

    company_by = _company_map(report_data.get("company_reports") or [])
    stocks_in = report_data.get("stock_analysis") or []
    if not stocks_in:
        stocks_in = [
            {
                "name": e["name"],
                "code": e["ticker"],
                "ticker": e["ticker"],
                "sector_key": e["sector_key"],
                "sector_name": e["sector_name"],
                "theme": e["sector_name"],
                "sector_order": e["sector_order"],
                "stock_order": e["stock_order"],
                "price": NA,
                "target_price": NA,
                "foreign_net_eok": NA,
                "high_52": NA,
                "label": NA,
                "label_reason": "",
                "verdict_class": "hold",
                "company_summary": "",
            }
            for e in build_watchlist_stock_pool(pipeline)
        ]
        stocks_in = sort_kr_focus_stocks(stocks_in)

    stocks = [_map_stock(r, company_by_ticker=company_by, pipeline=pipeline) for r in stocks_in]
    if stocks and stocks[0].get("sector_order") is None:
        stocks = sorted(
            stocks,
            key=lambda s: (
                stock_filter_options().index(s.get("sector_name", ""))
                if s.get("sector_name") in stock_filter_options()
                else 99,
                0 if "후회" in str(s.get("verdict_badge", "")) else 1,
                str(s.get("name", "")),
            ),
        )
    stock_filters = stock_filter_options()

    updated = now.strftime("%H:%M") + " 업데이트"

    ctx: dict[str, Any] = {
        "market_type": "KR",
        "title": "투자 인사이트",
        "market_meta": {
            "market": "한국시장",
            "date": f"{now.strftime('%Y-%m-%d')} {_weekday_ko(now)}",
            "updated_at": updated,
        },
        "indices": index_rows,
        "market_commentary": market_comment,
        "market_commentary_source": market_comment_src,
        "sectors": sectors,
        "sector_filter_options": sector_filters,
        "stocks": stocks,
        "stock_filter_options": stock_filters,
        "disclaimer": "투자 참고용이며, 데이터·AI 코멘트는 실시간과 다를 수 있음.",
        "_meta": {
            "indices": index_meta,
            "sectors": sector_meta,
            "generated_at": now.isoformat(timespec="seconds"),
        },
    }
    ctx["report_data_json"] = json.dumps(
        build_report_data_js(ctx, report_data=report_data, pipeline=pipeline),
        ensure_ascii=False,
    )
    return ctx


def render_kr_market_page(
    report_data: dict[str, Any],
    output_path: str | Path,
    *,
    market_data: dict[str, Any] | None = None,
    pipeline: dict[str, Any] | None = None,
) -> str:
    from .render import render_kr_market

    ctx = build_kr_market_context(report_data, market_data=market_data, pipeline=pipeline)
    return render_kr_market(ctx, output_path)
