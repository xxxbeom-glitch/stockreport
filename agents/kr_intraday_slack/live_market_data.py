"""KIS / pykrx 라이브 시세·수급 수집 (관심종목 전용)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from data.kr_market import get_foreign_net_by_ticker, get_trading_date
from data.kis_client import get_52w_high_low as get_kis_52w
from data.kis_client import get_price as get_kis_price
from data.utils import safe_float

logger = logging.getLogger("kr_intraday.market_data")

_REQUIRED_FIELDS = ("current_price", "prev_close", "day_high", "day_low", "trading_value")

_trading_date_cache: str | None = None


def _trading_date() -> str:
    global _trading_date_cache
    if _trading_date_cache is None:
        _trading_date_cache = get_trading_date()
    return _trading_date_cache


def _fmt_won(value: int | float) -> str:
    return f"{int(round(value)):,}원"


def _won_to_eok(value: float | None) -> int | None:
    """원 단위 순매수 → 억 원 정수 (표시용)."""
    if value is None:
        return None
    v = float(value)
    if abs(v) < 1_000_000:
        return int(round(v))
    return int(round(v / 100_000_000))


def _resolve_market(ticker: str) -> str:
    """KOSPI / KOSDAQ (pykrx 목록 기준)."""
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception as exc:
        logger.warning("[%s] pykrx 미설치 — 시장 구분 기본 KOSPI: %s", ticker, exc)
        return "KOSPI"

    date = _trading_date()
    code = ticker.zfill(6)
    for market in ("KOSPI", "KOSDAQ", "KONEX"):
        try:
            tickers = pykrx_stock.get_market_ticker_list(date, market=market)
            if code in [str(t).zfill(6) for t in tickers]:
                return market
        except Exception as exc:
            logger.debug("[%s] 시장 목록 조회 실패 (%s): %s", ticker, market, exc)
    return "KOSPI"


def _kis_quote_fields(ticker: str) -> tuple[dict[str, Any], list[str]]:
    """KIS 현재가 API → 당일 시세 필드."""
    errors: list[str] = []
    out: dict[str, Any] = {"source": "none"}
    quote = get_kis_price(ticker)
    if not quote:
        errors.append("KIS inquire-price: 응답 없음")
        return out, errors

    raw = quote.get("raw") or {}
    if not isinstance(raw, dict) or not raw:
        errors.append("KIS inquire-price: output 비어 있음")
        return out, errors

    current = safe_float(quote.get("price") or raw.get("stck_prpr"), 0.0)
    prev_close = safe_float(
        raw.get("prdy_clpr") or raw.get("stck_prdy_clpr") or raw.get("stck_sdpr"),
        0.0,
    )
    day_high = safe_float(raw.get("stck_hgpr") or raw.get("hgpr") or raw.get("stck_mxpr"), 0.0)
    day_low = safe_float(raw.get("stck_lwpr") or raw.get("lwpr") or raw.get("stck_llam"), 0.0)
    trading_value = safe_float(
        raw.get("acml_tr_pbmn") or raw.get("acml_tr_amt") or raw.get("acml_tr_prsm"),
        0.0,
    )

    if current <= 0:
        errors.append("KIS: 현재가 0 또는 없음 (장외·미거래·API 제한)")
        current = 0
    if prev_close <= 0:
        errors.append("KIS: 전일종가 없음 (pykrx 보완 예정)")
    if day_high <= 0:
        errors.append("KIS: 당일고가 없음 (pykrx 보완 예정)")
    if day_low <= 0:
        errors.append("KIS: 당일저가 없음 (pykrx 보완 예정)")
    if trading_value <= 0:
        errors.append("KIS: 누적거래대금 없음 (pykrx 보완 예정)")

    out.update(
        {
            "source": "kis",
            "current_price": int(current) if current > 0 else None,
            "prev_close": int(prev_close) if prev_close > 0 else None,
            "day_high": int(day_high) if day_high > 0 else None,
            "day_low": int(day_low) if day_low > 0 else None,
            "trading_value": int(trading_value) if trading_value > 0 else None,
            "change_rate": safe_float(quote.get("change_rate"), 0.0),
            "volume": safe_float(quote.get("volume") or raw.get("acml_vol"), 0.0),
        }
    )
    return out, errors


def _pykrx_ohlc_fields(ticker: str, market: str) -> tuple[dict[str, Any], list[str]]:
    """pykrx 당일/전일 OHLC·거래대금 보완."""
    errors: list[str] = []
    out: dict[str, Any] = {}
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception as exc:
        errors.append(f"pykrx import 실패: {exc}")
        return out, errors

    date = _trading_date()
    code = ticker.zfill(6)
    try:
        today_frame = pykrx_stock.get_market_ohlcv(date, market=market)
        if today_frame is None or code not in today_frame.index:
            errors.append(f"pykrx get_market_ohlcv: {date}/{market}에 {code} 없음")
        else:
            row = today_frame.loc[code]
            close = safe_float(row.get("종가"), 0.0)
            high = safe_float(row.get("고가"), 0.0)
            low = safe_float(row.get("저가"), 0.0)
            tv = safe_float(row.get("거래대금"), 0.0)
            if close > 0:
                out.setdefault("current_price", int(close))
            if high > 0:
                out.setdefault("day_high", int(high))
            if low > 0:
                out.setdefault("day_low", int(low))
            if tv > 0:
                out.setdefault("trading_value", int(tv))
            if "source" not in out or out.get("source") == "none":
                out["source"] = "pykrx"
    except Exception as exc:
        errors.append(f"pykrx get_market_ohlcv 예외: {exc}")

    try:
        dt = datetime.strptime(date, "%Y%m%d")
        start = (dt - timedelta(days=10)).strftime("%Y%m%d")
        hist = pykrx_stock.get_market_ohlcv_by_date(start, date, code)
        if hist is None or len(hist) < 2:
            errors.append(f"pykrx get_market_ohlcv_by_date: 이력 부족 ({len(hist) if hist is not None else 0}행)")
        else:
            prev = safe_float(hist["종가"].iloc[-2], 0.0)
            if prev > 0:
                out.setdefault("prev_close", int(prev))
            if len(hist) >= 1:
                out.setdefault("high_52w", int(safe_float(hist["고가"].max(), 0.0)))
    except Exception as exc:
        errors.append(f"pykrx OHLC 이력 예외: {exc}")

    return out, errors


def _volume_ratio(ticker: str) -> tuple[float | None, str | None]:
    try:
        from agents.watchlist_data import _kr_volume_ratio

        ratio = _kr_volume_ratio(ticker.zfill(6))
        if ratio is None:
            return None, "pykrx 거래량비율(20일): 계산 불가"
        return ratio, None
    except Exception as exc:
        return None, f"거래량비율 예외: {exc}"


def _investor_flow(ticker: str, market: str) -> tuple[int | None, int | None, list[str]]:
    """외국인·기관 순매수 (억 원 정수, 실패 시 None + 로그)."""
    warnings: list[str] = []
    foreign_eok: int | None = None
    inst_eok: int | None = None

    foreign_raw = get_foreign_net_by_ticker(ticker, market=market)
    if foreign_raw is None:
        warnings.append("외국인 순매수: KIS/pykrx 모두 없음")
    else:
        foreign_eok = _won_to_eok(foreign_raw)

    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        date = _trading_date()
        code = ticker.zfill(6)
        if hasattr(pykrx_stock, "get_market_trading_value_by_ticker"):
            frame = pykrx_stock.get_market_trading_value_by_ticker(date, market=market)
            if frame is not None and code in frame.index:
                if "기관" in frame.columns:
                    inst_eok = _won_to_eok(safe_float(frame.loc[code, "기관"], 0.0))
                else:
                    warnings.append("pykrx 거래대금: '기관' 컬럼 없음")
            else:
                warnings.append(f"pykrx 거래대금: {date} {code} 없음")
        else:
            warnings.append("pykrx get_market_trading_value_by_ticker 미지원")
    except Exception as exc:
        warnings.append(f"기관 순매수 pykrx 예외: {exc}")

    return foreign_eok, inst_eok, warnings


def fetch_live_watchlist_row(entry: dict[str, Any]) -> dict[str, Any]:
    """
    관심종목 1건 라이브 수집.
    실패 필드는 errors에 기록하고 data_complete=False (더미 대체 없음).
    """
    ticker = str(entry.get("ticker", "")).zfill(6)
    name = entry.get("name", ticker)
    if not ticker or not ticker.isdigit():
        msg = f"[{name}] 티커 없음"
        logger.error(msg)
        return {
            **entry,
            "ticker": ticker,
            "data_complete": False,
            "live": True,
            "fetch_errors": [msg],
            "price_source": "none",
        }

    market = _resolve_market(ticker)
    merged: dict[str, Any] = {
        "ticker": ticker,
        "name": name,
        "sector_key": entry.get("sector_key"),
        "sector_name": entry.get("sector_name"),
        "business": entry.get("business", ""),
        "selection_reason": entry.get("selection_reason", ""),
        "market": market,
        "live": True,
    }
    all_errors: list[str] = []

    kis_data, kis_err = _kis_quote_fields(ticker)
    kis_notes = list(kis_err)
    for k, v in kis_data.items():
        if v is not None and k != "source":
            merged[k] = v
    merged["price_source"] = kis_data.get("source", "none")

    pykrx_data, pykrx_err = _pykrx_ohlc_fields(ticker, market)
    for k, v in pykrx_data.items():
        if v is not None and merged.get(k) in (None, 0, ""):
            merged[k] = v
    if merged.get("price_source") == "none" and pykrx_data.get("source"):
        merged["price_source"] = pykrx_data["source"]
    if pykrx_err and merged.get("price_source") == "kis":
        for note in pykrx_err:
            logger.debug("[%s] pykrx 보완 참고: %s", ticker, note)

    w52 = get_kis_52w(ticker)
    if w52:
        merged["high_52w"] = int(safe_float(w52.get("high_52"), 0.0)) or merged.get("high_52w")
    elif merged.get("high_52w"):
        pass
    else:
        all_errors.append("52주 최고가: KIS/pykrx 없음")

    vol_ratio, vol_err = _volume_ratio(ticker)
    if vol_ratio is not None:
        merged["volume_ratio"] = vol_ratio
    if vol_err:
        all_errors.append(vol_err)

    foreign_eok, inst_eok, flow_warn = _investor_flow(ticker, market)
    for w in flow_warn:
        logger.warning("[%s] %s", ticker, w)
    merged["foreign_net_eok"] = foreign_eok
    merged["inst_net_eok"] = inst_eok

    missing = [f for f in _REQUIRED_FIELDS if not merged.get(f)]
    if missing:
        all_errors.append(f"필수 필드 누락: {', '.join(missing)}")
    elif kis_notes:
        logger.info("[%s] KIS 부분 필드 — pykrx로 보완 완료", ticker)

    current = merged.get("current_price")
    prev = merged.get("prev_close")
    day_high = merged.get("day_high")
    day_low = merged.get("day_low")
    high_52 = merged.get("high_52w") or day_high

    if current and day_high and day_high > 0:
        merged["pullback_from_high_pct"] = round(
            max(0.0, (1.0 - float(current) / float(day_high)) * 100.0),
            2,
        )
    else:
        merged["pullback_from_high_pct"] = None

    tv = merged.get("trading_value")
    merged["trading_value_fmt"] = _fmt_won(tv) if tv else None
    if current:
        merged["current_price_fmt"] = _fmt_won(current)
    if high_52:
        merged["high_52w_fmt"] = _fmt_won(high_52)
    if prev and current:
        merged["target_price"] = int(prev * 1.05)
        merged["target_price_fmt"] = _fmt_won(merged["target_price"])

    merged["trading_value_vs_3m"] = merged.get("volume_ratio")
    merged["data_complete"] = len(missing) == 0
    merged["fetch_errors"] = all_errors

    if all_errors:
        logger.error("[%s %s] live 수집 실패/부분실패: %s", ticker, name, "; ".join(all_errors))
    else:
        logger.info(
            "[%s %s] live OK source=%s price=%s tv=%s foreign_eok=%s inst_eok=%s",
            ticker,
            name,
            merged.get("price_source"),
            merged.get("current_price_fmt"),
            merged.get("trading_value_fmt"),
            foreign_eok,
            inst_eok,
        )

    return merged
