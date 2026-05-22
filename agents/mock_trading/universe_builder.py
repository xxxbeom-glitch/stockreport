# -*- coding: utf-8 -*-
"""관심 산업 종목풀 → 주간 가격·유동성 필터 후보군."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from agents.mock_trading.models import (
    AI_INPUT_CANDIDATE_TARGET_MAX,
    MAX_DISPLAY_PRICE,
    MIN_AVG_TRADING_VALUE_5D_WON,
    MIN_DAILY_TRADING_VALUE_WON,
    SECTOR_GROUPS,
    SECTOR_KEYWORDS,
    SECTOR_LABELS,
    empty_candidate,
)
from data.api_env import ensure_env_loaded
from data.kr_market import get_trading_date
from data.kis_client import get_price as get_kis_price

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET_UNIVERSE_PATH = ROOT / "data" / "mock_trading" / "target_sector_universe.json"

UniverseMode = Literal["target_sector", "keyword_discovery"]


def _pykrx_stock():
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        return pykrx_stock
    except Exception:
        return None


def list_kosdaq_tickers(trading_date: str | None = None) -> tuple[list[str], str | None]:
    """pykrx 코스닥 전체 티커 목록. (tickers, error)."""
    pykrx = _pykrx_stock()
    if pykrx is None:
        return [], "pykrx 미설치 — 코스닥 전체 목록 확보 불가"

    date = trading_date or get_trading_date()
    try:
        tickers = pykrx.get_market_ticker_list(date, market="KOSDAQ")
        codes = [str(t).zfill(6) for t in tickers]
        return codes, None
    except Exception as exc:
        return [], f"pykrx get_market_ticker_list 실패: {type(exc).__name__}"


def ticker_name_map(tickers: list[str], trading_date: str | None = None) -> dict[str, str]:
    pykrx = _pykrx_stock()
    if pykrx is None:
        return {t: t for t in tickers}
    date = trading_date or get_trading_date()
    out: dict[str, str] = {}
    for code in tickers:
        try:
            out[code] = str(pykrx.get_market_ticker_name(code)).strip() or code
        except Exception:
            out[code] = code
    return out


def classify_sector_groups(name: str) -> list[str]:
    """종목명 키워드 기반 산업군 (보조 discovery 전용, 기본 경로 아님)."""
    matched: list[str] = []
    upper = name.upper()
    for group in SECTOR_GROUPS:
        for kw in SECTOR_KEYWORDS.get(group, ()):
            if kw.upper() in upper or kw in name:
                matched.append(group)
                break
    return matched


def _primary_sector(groups: list[str]) -> str:
    if not groups:
        return ""
    for g in SECTOR_GROUPS:
        if g in groups:
            return g
    return groups[0]


def load_target_sector_included(
    path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    """
    target_sector_universe.json 에서 review_status==included 만 로드.
    티커 기준 병합(sector_keys 합침).
    """
    p = path or DEFAULT_TARGET_UNIVERSE_PATH
    if not p.is_file():
        return [], {}, f"파일 없음: {p}"

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [], {}, f"JSON 로드 실패: {type(exc).__name__}"

    by_ticker: dict[str, dict[str, Any]] = {}
    for sector in data.get("sectors") or []:
        if not isinstance(sector, dict):
            continue
        for stock in sector.get("stocks") or []:
            if not isinstance(stock, dict):
                continue
            if str(stock.get("review_status") or "") != "included":
                continue
            code = str(stock.get("ticker") or "").zfill(6)
            if not code or code == "000000":
                continue
            keys = list(stock.get("sector_keys") or [])
            sk = str(sector.get("sector_key") or "")
            if sk and sk not in keys:
                keys.append(sk)
            if code in by_ticker:
                merged = set(by_ticker[code].get("sector_keys") or [])
                merged.update(keys)
                by_ticker[code]["sector_keys"] = sorted(merged)
            else:
                by_ticker[code] = {**stock, "ticker": code, "sector_keys": sorted(set(keys))}

    meta = {
        "generated_at": data.get("generated_at"),
        "classification_method": data.get("classification_method"),
        "trading_date": data.get("trading_date"),
        "included_total": len(by_ticker),
    }
    return list(by_ticker.values()), meta, None


def fetch_kosdaq_ohlcv_frame(trading_date: str | None = None) -> tuple[Any | None, str | None]:
    pykrx = _pykrx_stock()
    if pykrx is None:
        return None, "pykrx 미설치"
    date = trading_date or get_trading_date()
    try:
        frame = pykrx.get_market_ohlcv(date, market="KOSDAQ")
        if frame is None or len(frame) < 1:
            return None, f"pykrx KOSDAQ OHLCV 빈 프레임 ({date})"
        return frame, None
    except Exception as exc:
        return None, f"pykrx OHLCV 실패: {type(exc).__name__}"


def _fetch_kis_quote(ticker: str) -> tuple[int | None, dict[str, Any] | None, str | None]:
    try:
        quote = get_kis_price(ticker.zfill(6))
    except Exception as exc:
        return None, None, f"kis:{type(exc).__name__}"
    if not quote or quote.get("price") is None:
        return None, quote, "kis:no_quote"
    try:
        p = int(round(float(quote["price"])))
    except (TypeError, ValueError):
        return None, quote, "kis:parse_error"
    if p <= 0:
        return None, quote, "kis:zero"
    return p, quote, None


def _verify_kosdaq_market(
    ticker: str,
    trading_date: str,
    resolve_pykrx_market: Any,
) -> tuple[str, str, str | None]:
    """
    (market_check_status, market_label, exclude_reason)
    verified → KOSDAQ only.
    """
    try:
        m = resolve_pykrx_market(
            ticker, requested_market="KOSDAQ", trading_date=trading_date
        )
    except Exception as exc:
        return "unverified", "", f"pykrx_market_error:{type(exc).__name__}"

    resolved = str(m.get("resolved_market") or "").strip().upper()
    in_kosdaq = m.get("in_kosdaq") is True

    if resolved == "KOSDAQ" and in_kosdaq:
        return "verified", "KOSDAQ", None
    if resolved == "KOSPI":
        return "kospi", "KOSPI", f"pykrx 시장=KOSPI (코스닥 전용 제외)"
    if resolved:
        return "unverified", resolved, f"pykrx 시장={resolved} (KOSDAQ 미확인)"
    return "unverified", "", "pykrx 시장 미확인"


def _kis_risk_assessment(quote: dict[str, Any] | None) -> dict[str, Any]:
    """
    KIS inquire-price raw 기준 위험 판정.
    제외: 거래정지, 관리종목, 투자경고(02), 투자위험(03)
    투자주의(01): warning_flag만, 제외 안 함
    """
    out: dict[str, Any] = {
        "exclude": False,
        "exclude_reason": None,
        "warning_flag": None,
        "risk_check_status": "unverified",
        "tradable": None,
        "notes": [],
    }
    if not quote:
        return out

    raw = quote.get("raw") or {}
    if not isinstance(raw, dict):
        return out

    out["risk_check_status"] = "verified"

    halt = str(raw.get("temp_stop_yn") or raw.get("stck_stop_yn") or "").upper()
    if halt in ("Y", "1"):
        out["exclude"] = True
        out["exclude_reason"] = "trading_halt"
        out["tradable"] = False
        out["notes"].append("거래정지(temp_stop_yn)")
        return out

    managed = str(raw.get("mang_issu_cls_code") or "").upper()
    if managed in ("Y", "1"):
        out["exclude"] = True
        out["exclude_reason"] = "managed_stock"
        out["notes"].append("관리종목(mang_issu_cls_code)")
        return out

    warn_cls = str(raw.get("mrkt_warn_cls_code") or "").strip().zfill(2)
    if warn_cls == "03":
        out["exclude"] = True
        out["exclude_reason"] = "investment_risk"
        out["notes"].append("투자위험(mrkt_warn_cls_code=03)")
        return out
    if warn_cls == "02":
        out["exclude"] = True
        out["exclude_reason"] = "investment_warning"
        out["notes"].append("투자경고(mrkt_warn_cls_code=02)")
        return out
    if warn_cls == "01":
        out["warning_flag"] = "investment_caution"
        out["notes"].append("투자주의(mrkt_warn_cls_code=01)")

    invt = str(raw.get("invt_caful_yn") or "").upper()
    if invt in ("Y", "1"):
        if not out["warning_flag"]:
            out["warning_flag"] = "investment_caution"
        out["notes"].append("투자주의(invt_caful_yn)")

    out["tradable"] = True if not out["exclude"] else False
    return out


def _trading_values_from_ohlcv(ohlcv: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    """(avg_trading_value_5d, last_trading_value)"""
    tvs = [float(r.get("trading_value") or 0) for r in ohlcv if (r.get("trading_value") or 0) > 0]
    if not tvs:
        return None, None
    last_tv = int(tvs[-1])
    window = tvs[-5:] if len(tvs) >= 5 else tvs
    avg_5d = int(sum(window) / len(window))
    return avg_5d, last_tv


def _collect_low_cost_metrics(
    ticker: str,
    name: str,
    sector_keys: list[str],
    *,
    collect_foreign_flow: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    """(metrics dict, ohlcv rows or None)"""
    metrics: dict[str, Any] = {
        "return_5d_pct": None,
        "return_10d_pct": None,
        "volume_change": None,
        "trading_value_change": None,
        "avg_trading_value_5d": None,
        "last_trading_value": None,
        "liquidity_rank": None,
        "foreign_flow": None,
        "institution_flow": None,
    }
    ohlcv: list[dict[str, Any]] | None = None
    try:
        from agents.weekly_watchlist_update.weekly_metrics import (
            compute_stock_metrics,
            fetch_ohlcv_history,
        )

        ohlcv_rows, _fetch_meta = fetch_ohlcv_history(ticker, market="KOSDAQ")
        primary = sector_keys[0] if sector_keys else ""
        computed = compute_stock_metrics(
            {"ticker": ticker, "symbol": name, "sector": primary},
            ohlcv_rows,
        )
        metrics["return_5d_pct"] = computed.get("return_5d")
        metrics["return_10d_pct"] = computed.get("return_10d")
        metrics["volume_change"] = computed.get("volume_ratio")
        metrics["trading_value_change"] = computed.get("tv_5d_avg")
        avg_5d, last_tv = _trading_values_from_ohlcv(ohlcv_rows)
        metrics["avg_trading_value_5d"] = avg_5d
        metrics["last_trading_value"] = last_tv
    except Exception as exc:
        logger.debug("%s metrics 실패: %s", ticker, type(exc).__name__)

    if collect_foreign_flow:
        try:
            from data.kr_market import get_foreign_net_by_ticker

            fn = get_foreign_net_by_ticker(ticker, market="KOSDAQ")
            if fn is not None:
                metrics["foreign_flow"] = fn
        except Exception:
            pass

    return metrics, ohlcv


def _candidate_from_included_stock(stock: dict[str, Any]) -> dict[str, Any]:
    code = str(stock.get("ticker") or "").zfill(6)
    name = str(stock.get("name") or code)
    sector_keys = list(stock.get("sector_keys") or [])
    primary = sector_keys[0] if sector_keys else ""
    row = empty_candidate(code, name, primary)
    row["sector_keys"] = sector_keys
    row["business_summary"] = str(stock.get("business_summary") or "")
    row["inclusion_reason"] = str(stock.get("inclusion_reason") or "")
    row["classification_confidence"] = str(
        stock.get("classification_confidence") or "high"
    )
    row["filters"]["business_included"] = True
    return row


def build_universe_from_target_sector(
    *,
    use_kis_prices: bool = True,
    trading_date: str | None = None,
    target_universe_path: Path | None = None,
    collect_metrics: bool = True,
    collect_foreign_flow: bool = True,
) -> dict[str, Any]:
    """included 종목풀 → KIS 가격·메트릭 필터 후보."""
    ensure_env_loaded()
    now = datetime.now(KST)
    date = trading_date or get_trading_date()

    included, src_meta, load_err = load_target_sector_included(target_universe_path)
    empty_result = {
        "candidates": [],
        "excluded_by_market": [],
        "excluded_by_price": [],
        "excluded_by_risk": [],
        "excluded_by_liquidity": [],
        "lookup_failures": [],
    }

    if load_err:
        return {
            **empty_result,
            "universe_summary": {"included_total": 0},
            "errors": [load_err],
            "notes": [],
            "kosdaq_available": False,
        }

    if not use_kis_prices:
        return {
            **empty_result,
            "universe_summary": {"included_total": len(included)},
            "errors": ["target_sector 모드는 KIS 현재가 필수 (--use-kis-prices)"],
            "notes": [],
            "kosdaq_available": True,
        }

    summary: dict[str, Any] = {
        "included_total": len(included),
        "market_verified_kosdaq": 0,
        "market_excluded": 0,
        "market_unverified": 0,
        "price_checked": 0,
        "price_under_59000": 0,
        "price_excluded": 0,
        "price_lookup_failed": 0,
        "risk_excluded": 0,
        "liquidity_checked": 0,
        "liquidity_excluded": 0,
        "final_candidate_count": 0,
        "liquidity_threshold_won": MIN_AVG_TRADING_VALUE_5D_WON,
        "ai_input_target_max": AI_INPUT_CANDIDATE_TARGET_MAX,
        "trading_date": date,
        "source_universe_generated_at": src_meta.get("generated_at"),
        "generated_at": now.isoformat(timespec="seconds"),
        "price_source_mode": "kis",
    }
    errors: list[str] = []
    notes: list[str] = []

    try:
        from agents.weekly_watchlist_update.weekly_metrics import resolve_pykrx_market
    except Exception:
        resolve_pykrx_market = None  # type: ignore

    if resolve_pykrx_market is None:
        errors.append("resolve_pykrx_market import 실패 — 코스닥 시장 검증 불가")

    candidates: list[dict[str, Any]] = []
    excluded_by_market: list[dict[str, Any]] = []
    excluded_by_price: list[dict[str, Any]] = []
    excluded_by_risk: list[dict[str, Any]] = []
    excluded_by_liquidity: list[dict[str, Any]] = []
    lookup_failures: list[dict[str, Any]] = []
    price_pass_pool: list[dict[str, Any]] = []

    for stock in included:
        code = str(stock.get("ticker") or "").zfill(6)
        name = str(stock.get("name") or code)
        row = _candidate_from_included_stock(stock)

        if resolve_pykrx_market is None:
            summary["market_unverified"] = int(summary["market_unverified"]) + 1
            row["market_check_status"] = "unverified"
            lookup_failures.append(
                {
                    "ticker": code,
                    "name": name,
                    "reason": "market_check_unavailable",
                }
            )
            continue

        m_status, market_label, m_reason = _verify_kosdaq_market(
            code, date, resolve_pykrx_market
        )
        row["market_check_status"] = m_status
        row["market"] = market_label or "KOSDAQ"

        if m_status != "verified":
            if m_status == "kospi":
                summary["market_excluded"] = int(summary["market_excluded"]) + 1
                excluded_by_market.append(
                    {
                        "ticker": code,
                        "name": name,
                        "resolved_market": market_label,
                        "reason": m_reason or "KOSPI",
                    }
                )
            else:
                summary["market_unverified"] = int(summary["market_unverified"]) + 1
                lookup_failures.append(
                    {
                        "ticker": code,
                        "name": name,
                        "reason": m_reason or "market_unverified",
                    }
                )
            continue

        summary["market_verified_kosdaq"] = int(summary["market_verified_kosdaq"]) + 1
        row["market"] = "KOSDAQ"

        price, quote, kis_err = _fetch_kis_quote(code)
        summary["price_checked"] = int(summary["price_checked"]) + 1

        if kis_err or price is None:
            summary["price_lookup_failed"] = int(summary["price_lookup_failed"]) + 1
            lookup_failures.append(
                {"ticker": code, "name": name, "reason": kis_err or "kis:no_price"}
            )
            continue

        row["current_price"] = price
        row["price_source"] = "kis"
        row["price_updated_at"] = now.isoformat(timespec="seconds")
        row["filters"]["price_under_59000"] = price <= MAX_DISPLAY_PRICE

        risk = _kis_risk_assessment(quote)
        row["filters"]["tradable"] = risk.get("tradable")
        row["filters"]["risk_check_status"] = risk.get("risk_check_status")
        row["filters"]["warning_flag"] = risk.get("warning_flag")
        if risk.get("notes"):
            row["filters"]["risk_notes"] = list(risk["notes"])

        if risk.get("exclude"):
            summary["risk_excluded"] = int(summary["risk_excluded"]) + 1
            excluded_by_risk.append(
                {
                    "ticker": code,
                    "name": name,
                    "current_price": price,
                    "reason": risk.get("exclude_reason"),
                    "detail": "; ".join(risk.get("notes") or []),
                }
            )
            continue

        if price > MAX_DISPLAY_PRICE:
            summary["price_excluded"] = int(summary["price_excluded"]) + 1
            excluded_by_price.append(
                {
                    "ticker": code,
                    "name": name,
                    "current_price": price,
                    "sector_keys": row.get("sector_keys"),
                    "reason": f"current_price {price} > {MAX_DISPLAY_PRICE}",
                }
            )
            continue

        summary["price_under_59000"] = int(summary["price_under_59000"]) + 1
        price_pass_pool.append(row)

    # 유동성: 가격 통과 코스닥 종목만
    liquidity_rows: list[tuple[dict[str, Any], int | None]] = []
    for row in price_pass_pool:
        code = str(row["ticker"]).zfill(6)
        name = str(row.get("name") or code)
        summary["liquidity_checked"] = int(summary["liquidity_checked"]) + 1

        if collect_metrics:
            metrics, _ohlcv = _collect_low_cost_metrics(
                code,
                name,
                row.get("sector_keys") or [],
                collect_foreign_flow=collect_foreign_flow,
            )
            row["metrics"] = metrics
            avg_5d = metrics.get("avg_trading_value_5d")
        else:
            avg_5d = None

        liquidity_rows.append((row, avg_5d if isinstance(avg_5d, int) else None))

    # 거래대금 순위 (통과 후보 기준, null은 하위)
    ranked = sorted(
        liquidity_rows,
        key=lambda x: (x[1] is not None, x[1] or 0),
        reverse=True,
    )
    rank = 0
    for row, avg_5d in ranked:
        rank += 1
        if row.get("metrics") is not None:
            row["metrics"]["liquidity_rank"] = rank

        if avg_5d is None:
            summary["liquidity_excluded"] = int(summary["liquidity_excluded"]) + 1
            excluded_by_liquidity.append(
                {
                    "ticker": row["ticker"],
                    "name": row.get("name"),
                    "avg_trading_value_5d": None,
                    "reason": "ohlcv_or_trading_value_unavailable",
                }
            )
            continue

        row["filters"]["liquidity_pass"] = avg_5d >= MIN_AVG_TRADING_VALUE_5D_WON
        if avg_5d < MIN_AVG_TRADING_VALUE_5D_WON:
            summary["liquidity_excluded"] = int(summary["liquidity_excluded"]) + 1
            excluded_by_liquidity.append(
                {
                    "ticker": row["ticker"],
                    "name": row.get("name"),
                    "avg_trading_value_5d": avg_5d,
                    "reason": f"avg_5d {avg_5d} < {MIN_AVG_TRADING_VALUE_5D_WON}",
                }
            )
            continue

        candidates.append(row)

    summary["final_candidate_count"] = len(candidates)
    by_sector: dict[str, int] = {g: 0 for g in SECTOR_GROUPS}
    for c in candidates:
        for sk in c.get("sector_keys") or []:
            if sk in by_sector:
                by_sector[sk] += 1
    summary["final_by_sector"] = by_sector

    if candidates:
        tvs = [
            int(c["metrics"]["avg_trading_value_5d"])
            for c in candidates
            if c.get("metrics", {}).get("avg_trading_value_5d") is not None
        ]
        if tvs:
            summary["liquidity_avg_5d_min"] = min(tvs)
            summary["liquidity_avg_5d_max"] = max(tvs)
            summary["liquidity_avg_5d_median"] = sorted(tvs)[len(tvs) // 2]

    if len(candidates) > AI_INPUT_CANDIDATE_TARGET_MAX:
        notes.append(
            f"최종 후보 {len(candidates)}종 > 권장 {AI_INPUT_CANDIDATE_TARGET_MAX}종 — "
            "추가 축소 기준 검토 필요 (이번 단계에서 임의 Top N 미적용)"
        )
        by_sec_tv: dict[str, list[int]] = {g: [] for g in SECTOR_GROUPS}
        for c in candidates:
            avg = (c.get("metrics") or {}).get("avg_trading_value_5d")
            if avg is None:
                continue
            for sk in c.get("sector_keys") or []:
                if sk in by_sec_tv:
                    by_sec_tv[sk].append(int(avg))
        summary["liquidity_by_sector_avg_5d"] = {
            sk: {
                "count": len(vals),
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
                "median": sorted(vals)[len(vals) // 2] if vals else None,
            }
            for sk, vals in by_sec_tv.items()
        }
    else:
        notes.append(
            f"최종 후보 {len(candidates)}종 — 뉴스·공시 보강 및 AI 입력 대상으로 사용 가능"
        )

    return {
        "candidates": candidates,
        "excluded_by_market": excluded_by_market,
        "excluded_by_price": excluded_by_price,
        "excluded_by_risk": excluded_by_risk,
        "excluded_by_liquidity": excluded_by_liquidity,
        "lookup_failures": lookup_failures,
        "universe_summary": summary,
        "errors": errors,
        "notes": notes,
        "kosdaq_available": True,
    }


def build_universe_keyword_discovery(
    *,
    use_kis_prices: bool = False,
    kis_price_limit: int = 0,
    trading_date: str | None = None,
) -> dict[str, Any]:
    """[보조] 코스닥 전체 종목명 키워드 매칭 — 기본 경로 아님."""
    ensure_env_loaded()
    now = datetime.now(KST)
    date = trading_date or get_trading_date()

    summary: dict[str, Any] = {
        "trading_date": date,
        "kosdaq_total_checked": 0,
        "industry_matched": 0,
        "price_under_59000": 0,
        "liquidity_pass_count": 0,
        "final_candidate_count": 0,
        "price_source_mode": "kis" if use_kis_prices else "pykrx_bulk",
        "generated_at": now.isoformat(timespec="seconds"),
        "mode": "keyword_discovery",
    }
    errors: list[str] = []
    notes: list[str] = ["keyword_discovery: 보조 탐색 모드"]

    tickers, list_err = list_kosdaq_tickers(date)
    if list_err:
        return {
            "candidates": [],
            "excluded_by_price": [],
            "lookup_failures": [],
            "universe_summary": summary,
            "errors": [list_err],
            "notes": notes,
            "kosdaq_available": False,
        }

    summary["kosdaq_total_checked"] = len(tickers)
    names = ticker_name_map(tickers, date)

    industry_rows: list[tuple[str, str, str]] = []
    for code in tickers:
        name = names.get(code, code)
        groups = classify_sector_groups(name)
        if not groups:
            continue
        industry_rows.append((code, name, _primary_sector(groups)))

    summary["industry_matched"] = len(industry_rows)
    ohlcv_frame, ohlcv_err = fetch_kosdaq_ohlcv_frame(date)
    if ohlcv_err and not use_kis_prices:
        errors.append(ohlcv_err)

    try:
        from agents.weekly_watchlist_update.weekly_metrics import resolve_pykrx_market
    except Exception:
        resolve_pykrx_market = None  # type: ignore

    candidates: list[dict[str, Any]] = []
    excluded_by_price: list[dict[str, Any]] = []
    lookup_failures: list[dict[str, Any]] = []
    kis_used = 0

    for code, name, sector_group in industry_rows:
        row = empty_candidate(code, name, sector_group)
        row["sector_keys"] = [sector_group]
        row["business_summary"] = SECTOR_LABELS.get(sector_group, "")
        row["filters"]["business_included"] = False

        if resolve_pykrx_market is not None:
            try:
                m = resolve_pykrx_market(code)
                if m.get("resolved_market") and m.get("resolved_market") != "KOSDAQ":
                    continue
            except Exception:
                pass

        price: int | None = None
        price_source = ""

        if use_kis_prices and (kis_price_limit <= 0 or kis_used < kis_price_limit):
            price, _, kis_err = _fetch_kis_quote(code)
            if kis_err:
                lookup_failures.append(
                    {"ticker": code, "name": name, "reason": kis_err}
                )
                continue
            price_source = "kis"
            kis_used += 1
        elif ohlcv_frame is not None:
            from data.utils import safe_float

            index_map = {str(i).zfill(6): i for i in ohlcv_frame.index}
            if code not in index_map:
                continue
            r = ohlcv_frame.loc[index_map[code]]
            close = safe_float(r.get("종가"), 0.0)
            if close <= 0:
                continue
            price = int(round(close))
            price_source = "pykrx"
        else:
            errors.append(f"{code}: 가격 소스 없음")
            continue

        row["current_price"] = price
        row["price_source"] = price_source
        row["price_updated_at"] = now.isoformat(timespec="seconds")
        row["filters"]["price_under_59000"] = price <= MAX_DISPLAY_PRICE

        if price > MAX_DISPLAY_PRICE:
            excluded_by_price.append(
                {
                    "ticker": code,
                    "name": name,
                    "current_price": price,
                    "reason": "price_over_limit",
                }
            )
            continue

        summary["price_under_59000"] = int(summary["price_under_59000"]) + 1
        row["filters"]["risk_check_status"] = "unverified"
        candidates.append(row)

    summary["final_candidate_count"] = len(candidates)
    if use_kis_prices:
        summary["kis_prices_fetched"] = kis_used

    return {
        "candidates": candidates,
        "excluded_by_price": excluded_by_price,
        "lookup_failures": lookup_failures,
        "universe_summary": summary,
        "errors": errors,
        "notes": notes,
        "kosdaq_available": True,
    }


def build_universe(
    *,
    universe_mode: UniverseMode = "target_sector",
    use_kis_prices: bool = False,
    kis_price_limit: int = 0,
    trading_date: str | None = None,
    target_universe_path: Path | None = None,
    collect_metrics: bool = True,
) -> dict[str, Any]:
    """
    후보군 생성.
    기본: target_sector_universe.json 의 included 종목 + KIS 가격 필터.
    """
    if universe_mode == "keyword_discovery":
        return build_universe_keyword_discovery(
            use_kis_prices=use_kis_prices,
            kis_price_limit=kis_price_limit,
            trading_date=trading_date,
        )
    return build_universe_from_target_sector(
        use_kis_prices=use_kis_prices,
        trading_date=trading_date,
        target_universe_path=target_universe_path,
        collect_metrics=collect_metrics,
    )
