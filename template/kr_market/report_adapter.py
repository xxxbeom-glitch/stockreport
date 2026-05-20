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
from data.kr_market import get_kis_sector_trading_value
from data.kr_watchlist import (
    build_watchlist_stock_pool,
    default_sector_flow,
    iter_watchlist_entries,
    load_kr_watchlist_raw,
    sort_kr_focus_stocks,
    stock_filter_options,
    watchlist_sectors_meta,
    SECTOR_ORDER,
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


def _sector_trading_sentiment(is_inflow: bool, flow_amount: str) -> str:
    """Figma 섹터 카드 '거래 분위기' 행."""
    if flow_amount != NA and "%" in flow_amount:
        return "거래대금 증가" if is_inflow else "거래대금 감소"
    return "거래대금 증가" if is_inflow else "거래대금 감소"


def _sector_kv_rows(
    *,
    is_inflow: bool,
    flow_amount: str,
    commentary: str,
    interest_3m: Any = None,
) -> list[dict[str, str]]:
    recent = commentary if commentary and commentary != AI_COMMENT_FALLBACK else NA
    return [
        {"label": "거래 분위기", "value": _sector_trading_sentiment(is_inflow, flow_amount)},
        {"label": "3개월 관심도", "value": _safe_str(interest_3m) if interest_3m is not None else NA},
        {"label": "최근 이슈", "value": recent},
    ]


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
    """관심 5섹터 고정(kr_watchlist.json) — 전체 시장 섹터 추천 미사용."""
    sector_flow = report_data.get("sector_flow") or default_sector_flow()
    hot = set(sector_flow.get("hot") or [])
    cold = set(sector_flow.get("cold") or [])
    chg_map: dict[str, float] = {} if _is_offline_render() else _sector_change_map()
    pulse = str(((pipeline or {}).get("engines") or {}).get("market_pulse", {}).get("pulse_summary", ""))
    used_pulse = False

    raw = load_kr_watchlist_raw()
    sectors = raw.get("sectors") or {}
    cards: list[dict[str, Any]] = []
    meta: dict[str, str] = {}

    for key in SECTOR_ORDER:
        block = sectors.get(key) or {}
        name = str(block.get("label", key))
        stock_names: list[str] = []
        for item in block.get("stocks") or []:
            if isinstance(item, dict):
                nm = str(item.get("name", "")).strip()
                if nm:
                    stock_names.append(nm)
            elif isinstance(item, str) and item.strip():
                stock_names.append(item.strip())

        if name in hot:
            is_inflow = True
        elif name in cold:
            is_inflow = False
        else:
            is_inflow = True

        comment, src = _sector_commentary(
            name,
            is_inflow=is_inflow,
            stock_names=stock_names,
            pipeline=pipeline,
            pulse="" if used_pulse else pulse,
        )
        used_pulse = used_pulse or bool(pulse)
        flow_amount = _sector_flow_label(name, is_inflow, chg_map)
        cards.append(
            {
                "name": name,
                "sector_key": name,
                "is_inflow": is_inflow,
                "flow_amount": flow_amount,
                "tag": "관심 종목" if stock_names else NA,
                "stock_names": stock_names,
                "commentary": comment,
                "commentary_source": src,
                "kv_rows": _sector_kv_rows(
                    is_inflow=is_inflow,
                    flow_amount=flow_amount,
                    commentary=comment,
                ),
            }
        )
        meta[name] = src

    return cards, stock_filter_options(), meta


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

    business_inline = str(row.get("business") or "").strip()
    company_text, company_src = _company_summary_text(company_by_ticker.get(key), pipeline=pipeline, ticker=key)
    if business_inline and business_inline != NA:
        company_text = format_ui_comment(business_inline)
        company_src = "rules"
    elif not company_text or company_text == COMPANY_SUMMARY_FALLBACK:
        inline = str(row.get("company_summary") or "").strip()
        if inline and inline != NA:
            company_text = format_ui_comment(inline)
            company_src = "ai"

    sector_key = str(row.get("sector_key") or "")
    sector_name = str(row.get("sector_name") or row.get("theme") or NA)
    target_price = row.get("target_price")

    price_raw = row.get("price")
    price_display = _safe_str(price_raw)
    if price_display != NA and not str(price_display).endswith("원"):
        try:
            price_display = f"{float(str(price_raw).replace(',', '')):,.0f}원"
        except (TypeError, ValueError):
            price_display = f"{price_display}원"

    metrics = [
        {"label": "목표가", "value": _safe_str(target_price)},
        {"label": "외국인 순매수", "value": _safe_str(row.get("foreign_net_eok"))},
        {"label": "52주 최고가", "value": _safe_str(row.get("high_52"))},
        {"label": "주요사업", "value": company_text},
    ]

    return {
        "name": row.get("name", NA),
        "ticker": ticker or NA,
        "sector_key": sector_key or NA,
        "sector_name": sector_name,
        "current_price": price_display,
        "price_tone": "up" if row.get("verdict_class") == "buy" else "neutral",
        "verdict_badge": label if label in VALID_LABELS else NA,
        "verdict_class": row.get("verdict_class", "hold"),
        "selection_reason": reason,
        "opinion_source": "ai" if reason != AI_COMMENT_FALLBACK else "fallback",
        "metrics": metrics,
        "company_summary": company_text,
        "company_summary_source": company_src,
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


def build_watchlist_verify_report_data() -> dict[str, Any]:
    """
    CI 검증용: data/kr_watchlist.json 전체 종목(25) 기준 report_data.
    sample_data.json 과 무관.
    """
    from agents.label_rules import LABEL_REGRET, LABEL_TIMING, label_to_badge_class

    rows: list[dict[str, Any]] = []
    for i, entry in enumerate(iter_watchlist_entries()):
        label = LABEL_REGRET if i % 2 == 0 else LABEL_TIMING
        base = 48_000 + (i * 1_150)
        reason = entry.get("selection_reason") or f"{entry['sector_name']} 관심종목.\n지표·수급 확인 예정."
        rows.append(
            {
                "name": entry["name"],
                "code": entry["ticker"],
                "ticker": entry["ticker"],
                "sector_key": entry["sector_key"],
                "sector_name": entry["sector_name"],
                "sector_order": entry["sector_order"],
                "stock_order": entry["stock_order"],
                "label": label,
                "verdict": label,
                "label_reason": reason,
                "verdict_class": label_to_badge_class(label),
                "price": f"{base:,}원",
                "target_price": f"{int(base * 1.08):,}원",
                "foreign_net_eok": f"+{80 + i * 7}억",
                "high_52": f"{int(base * 1.12):,}원",
                "business": entry.get("business", ""),
                "company_summary": entry.get("business", ""),
            }
        )

    flow = default_sector_flow()
    return {
        "report_type": "us_close_kr_before",
        "indices": {
            "KOSPI": {"value": "2,650.00", "change": "+0.42%", "is_up": True},
            "KOSDAQ": {"value": "850.12", "change": "-0.15%", "is_up": False},
        },
        "market_phase_reason": "코스피 소폭 상승.\n외국인 순매수는 제한적.",
        "sector_flow": flow,
        "stock_analysis": sort_kr_focus_stocks(rows),
    }


def build_static_preview_report_data() -> dict[str, Any]:
    """Offline UI 샘플용: watchlist 25종목 중 섹터별 1종목. Verify는 build_watchlist_verify_report_data."""
    from agents.label_rules import LABEL_REGRET, LABEL_TIMING, label_to_badge_class

    samples: list[dict[str, Any]] = []
    for i, entry in enumerate(iter_watchlist_entries()):
        if entry["stock_order"] != 0:
            continue
        label = LABEL_REGRET if entry["sector_order"] % 2 == 0 else LABEL_TIMING
        base = 52_000 + entry["sector_order"] * 3_200
        samples.append(
            {
                "name": entry["name"],
                "code": entry["ticker"],
                "ticker": entry["ticker"],
                "sector_key": entry["sector_key"],
                "sector_name": entry["sector_name"],
                "sector_order": entry["sector_order"],
                "stock_order": entry["stock_order"],
                "label": label,
                "label_reason": entry.get("selection_reason") or f"{entry['sector_name']} 관심종목.",
                "verdict_class": label_to_badge_class(label),
                "price": f"{base:,}원",
                "target_price": f"{int(base * 1.1):,}원",
                "foreign_net_eok": f"+{90 + i * 10}억",
                "high_52": f"{int(base * 1.15):,}원",
                "business": entry.get("business", ""),
                "company_summary": entry.get("business", ""),
            }
        )
    return {
        "report_type": "us_close_kr_before",
        "indices": {
            "KOSPI": {"value": "2,650.00", "change": "+0.42%", "is_up": True},
            "KOSDAQ": {"value": "850.12", "change": "-0.15%", "is_up": False},
        },
        "market_phase_reason": "코스피 소폭 상승.\n외국인 순매수는 제한적.",
        "sector_flow": default_sector_flow(),
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
                "business": e.get("business", ""),
                "company_summary": e.get("business", ""),
                "label_reason": e.get("selection_reason", ""),
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
