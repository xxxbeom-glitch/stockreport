"""Fact packages for SIMPLE_REPLAY candidates (as-of decision_date only)."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.trading.competition.constants import MAX_CANDIDATES
from src.trading.competition.decision.strategy_scouts import (
    scout_team_a,
    scout_team_b,
    scout_team_c,
    scout_team_d,
)
from src.trading.competition.ops.historical_seed import _load_foreign_net_map
from src.trading.simple_replay.leakage import decision_cutoff_iso

KST = ZoneInfo("Asia/SEOUL")
DART_PREFETCH_TOP_N = int(os.getenv("SIMPLE_REPLAY_DART_PREFETCH", "28"))
NEWS_PER_TICKER = int(os.getenv("SIMPLE_REPLAY_NEWS_PER_TICKER", "8"))


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = row.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _parse_pub_datetime(pub: str) -> datetime | None:
    if not pub:
        return None
    try:
        return parsedate_to_datetime(pub.strip()).astimezone(KST)
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_dart_as_of(ticker: str, as_of_yyyymmdd: str, *, max_items: int = 5) -> list[dict[str, Any]]:
    from data.dart_client import _dart_get, _resolve_corp_code, is_dart_configured

    if not is_dart_configured():
        return []
    corp = _resolve_corp_code(ticker)
    if not corp:
        return []
    end_dt = datetime.strptime(as_of_yyyymmdd, "%Y%m%d")
    start_dt = end_dt - timedelta(days=45)
    data = _dart_get(
        "list.json",
        {
            "corp_code": corp,
            "bgn_de": start_dt.strftime("%Y%m%d"),
            "end_de": as_of_yyyymmdd,
            "page_count": 30,
            "sort": "date",
            "sort_mth": "desc",
        },
    )
    if not data:
        return []
    items = data.get("list") or []
    out: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        rcept_dt = str(row.get("rcept_dt") or "")
        if rcept_dt and rcept_dt > as_of_yyyymmdd:
            continue
        rcept_no = str(row.get("rcept_no") or "").strip()
        title = str(row.get("report_nm") or "").strip()
        if not title:
            continue
        published = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}T09:00:00+09:00" if len(rcept_dt) == 8 else decision_cutoff_iso(as_of_yyyymmdd)
        out.append(
            {
                "type": "dart",
                "title": title,
                "published_at": published,
                "source_id": f"dart:{rcept_no or ticker}",
                "url": f"https://opendart.fss.or.kr/dsab007/detail.do?rcept_no={rcept_no}" if rcept_no else None,
            }
        )
    out.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return out[:max_items]


def fetch_news_as_of(
    ticker: str,
    name: str,
    as_of_yyyymmdd: str,
    *,
    max_items: int = NEWS_PER_TICKER,
) -> list[dict[str, Any]]:
    from data.naver_news_client import is_naver_news_configured, search_raw_news

    if not is_naver_news_configured():
        return []
    cutoff = datetime.strptime(as_of_yyyymmdd, "%Y%m%d").replace(
        hour=15, minute=30, second=0, tzinfo=KST
    )
    query = f"{name} {ticker}".strip()
    seen_titles: set[str] = set()
    rows: list[dict[str, Any]] = []
    for raw in search_raw_news(query, display=max(10, max_items * 2), sort="date"):
        title = re.sub(r"<[^>]+>", "", str(raw.get("title") or "")).strip()
        if not title:
            continue
        norm = re.sub(r"\s+", " ", title).lower()
        if norm in seen_titles:
            continue
        pub = _parse_pub_datetime(str(raw.get("pubDate") or ""))
        if pub is None:
            continue
        if pub > cutoff:
            continue
        seen_titles.add(norm)
        link = str(raw.get("link") or raw.get("originallink") or "").strip()
        rows.append(
            {
                "type": "news",
                "title": title,
                "published_at": pub.isoformat(),
                "source_id": f"news:{ticker}:{pub.strftime('%Y%m%d')}",
                "source": "naver_search_news",
                "url": link or None,
                "relevance": "direct" if ticker in title or (name and name[:2] in title) else "thematic_weak",
            }
        )
        if len(rows) >= max_items:
            break
    return rows


def load_inst_net_map(trading_date: str) -> tuple[dict[str, int], list[str]]:
    from src.trading.competition.replay.pykrx_safe import krx_credentials_configured, safe_pykrx_call

    if not krx_credentials_configured():
        return {}, ["inst_net_skipped:krx_credentials_missing"]
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception:
        return {}, ["inst_net:pykrx_unavailable"]

    out: dict[str, int] = {}
    errors: list[str] = []
    for market in ("KOSPI", "KOSDAQ"):
        frame, meta = safe_pykrx_call(
            f"trading_value_by_ticker:{market}:{trading_date}",
            lambda m=market: pykrx_stock.get_market_trading_value_by_ticker(trading_date, market=m),
        )
        if not meta.get("ok") or frame is None:
            errors.append(f"inst_net_unavailable:{market}")
            continue
        if "기관" not in getattr(frame, "columns", []):
            errors.append(f"inst_net_no_column:{market}")
            continue
        for ticker, row in frame.iterrows():
            code = str(ticker).zfill(6)
            try:
                out[code] = int(float(row["기관"]))
            except (TypeError, ValueError, KeyError):
                continue
    return out, errors


def attach_price_history(pool: list[dict[str, Any]], trading_date: str, *, sessions: int = 5) -> None:
    """Last N session closes/tv on each row (pykrx bulk, in-place)."""
    from src.trading.competition.replay.data_provider import list_trading_dates_result
    from src.trading.competition.replay.pykrx_safe import krx_credentials_configured, safe_pykrx_call

    if not krx_credentials_configured():
        return
    try:
        from pykrx import stock as pykrx_stock  # type: ignore
    except Exception:
        return

    start_probe = (datetime.strptime(trading_date, "%Y%m%d") - timedelta(days=sessions * 3 + 10)).strftime("%Y%m%d")
    cal = list_trading_dates_result(start_probe, trading_date)
    session_dates = [d for d in (cal.get("dates") or []) if d <= trading_date][-sessions:]
    if not session_dates:
        return

    by_date: dict[str, dict[str, dict[str, int]]] = {d: {} for d in session_dates}
    for date in session_dates:
        for market in ("KOSPI", "KOSDAQ"):
            frame, meta = safe_pykrx_call(
                f"get_market_ohlcv:{market}:{date}",
                lambda d=date, m=market: pykrx_stock.get_market_ohlcv(d, market=m),
            )
            if not meta.get("ok") or frame is None:
                continue
            for ticker, row in frame.iterrows():
                code = str(ticker).zfill(6)
                try:
                    by_date[date][code] = {
                        "close": int(float(row.get("종가", 0) or 0)),
                        "tv": int(float(row.get("거래대금", 0) or 0)),
                    }
                except (TypeError, ValueError):
                    continue

    for row in pool:
        code = str(row.get("ticker", "")).zfill(6)
        hist: list[dict[str, Any]] = []
        prev_close = None
        for d in session_dates:
            bar = by_date.get(d, {}).get(code)
            if not bar or bar["close"] <= 0:
                continue
            chg = None
            if prev_close and prev_close > 0:
                chg = round((bar["close"] - prev_close) / prev_close * 100, 2)
            hist.append(
                {
                    "date": d,
                    "close_price_krw": bar["close"],
                    "trading_value_krw": bar["tv"],
                    "change_rate_pct": chg,
                }
            )
            prev_close = bar["close"]
        row["price_history"] = hist
        row["price_history_basis"] = f"pykrx_bulk_sessions:{session_dates[0]}..{session_dates[-1]}"


def _price_facts(row: dict[str, Any], trading_date: str) -> dict[str, Any]:
    change = _f(row, "change_rate_pct")
    tv_ratio = _f(row, "tv_ratio_20d")
    avg_tv = int(_f(row, "avg_trading_value_20d_krw"))
    cur_tv = int(_f(row, "current_trading_value_krw"))
    signals: list[str] = []
    if tv_ratio >= 1.5:
        signals.append("volume_surge")
    if change >= 2.0:
        signals.append("price_breakout_up")
    elif change <= -5.0:
        signals.append("pullback")
    elif -5.0 < change <= -2.0:
        signals.append("mild_pullback")
    return {
        "as_of_date": trading_date,
        "current_price_krw": int(_f(row, "current_price_krw")),
        "change_rate_pct": round(change, 2) if change else 0.0,
        "tv_ratio_20d": round(tv_ratio, 2) if tv_ratio else None,
        "avg_trading_value_20d_krw": avg_tv,
        "current_trading_value_krw": cur_tv,
        "price_history": list(row.get("price_history") or []),
        "price_history_basis": row.get("price_history_basis"),
        "technical_signals": signals,
        "missing": [] if int(_f(row, "current_price_krw")) > 0 else ["current_price"],
    }


def _flow_facts(
    ticker: str,
    *,
    foreign_map: dict[str, float],
    inst_map: dict[str, int],
    foreign_errors: list[str],
) -> dict[str, Any]:
    foreign = foreign_map.get(ticker)
    inst = inst_map.get(ticker)
    missing: list[str] = []
    if foreign is None:
        missing.append("foreign_net")
    if inst is None:
        missing.append("inst_net")
    return {
        "foreign_net_krw": int(foreign) if foreign is not None else None,
        "inst_net_krw": inst if inst is not None else None,
        "foreign_net_status": "available" if foreign is not None else "missing",
        "inst_net_status": "available" if inst is not None else "missing",
        "collection_errors": foreign_errors[:3],
        "missing": missing,
        "note": "추정 금지 — None은 데이터 없음",
    }


def build_fact_package(
    row: dict[str, Any],
    trading_date: str,
    *,
    dart_items: list[dict[str, Any]] | None = None,
    news_items: list[dict[str, Any]] | None = None,
    foreign_map: dict[str, float] | None = None,
    inst_map: dict[str, int] | None = None,
    foreign_errors: list[str] | None = None,
) -> dict[str, Any]:
    ticker = str(row.get("ticker", "")).zfill(6)
    dart_items = dart_items if dart_items is not None else fetch_dart_as_of(ticker, trading_date)
    news_items = news_items if news_items is not None else fetch_news_as_of(
        ticker, str(row.get("name") or ticker), trading_date
    )
    return {
        "ticker": ticker,
        "name": str(row.get("name") or ticker),
        "market": row.get("market"),
        "as_of_datetime": decision_cutoff_iso(trading_date),
        "price": _price_facts(row, trading_date),
        "flow": _flow_facts(
            ticker,
            foreign_map=foreign_map or {},
            inst_map=inst_map or {},
            foreign_errors=foreign_errors or [],
        ),
        "dart_disclosures": dart_items,
        "dart_status": "available" if dart_items else ("unconfigured" if not __import__("data.dart_client", fromlist=["is_dart_configured"]).is_dart_configured() else "none_as_of_date"),
        "news": news_items,
        "news_status": "available" if news_items else "none_as_of_date",
    }


def prefetch_dart_news(
    pool: list[dict[str, Any]],
    trading_date: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], set[str]]:
    """Prefetch DART/news for top-N liquid names to bound API calls."""
    top = sorted(pool, key=lambda r: -int(_f(r, "avg_trading_value_20d_krw")))[:DART_PREFETCH_TOP_N]
    dart_cache: dict[str, list[dict[str, Any]]] = {}
    news_cache: dict[str, list[dict[str, Any]]] = {}
    material: set[str] = set()
    for row in top:
        t = str(row.get("ticker", "")).zfill(6)
        darts = fetch_dart_as_of(t, trading_date)
        dart_cache[t] = darts
        if darts:
            material.add(t)
        news = fetch_news_as_of(t, str(row.get("name") or t), trading_date)
        news_cache[t] = news
        if news:
            material.add(t)
    return dart_cache, news_cache, material


def build_team_candidate_inputs(
    pool: list[dict[str, Any]],
    trading_date: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Scouts + rich fact packages per team."""
    attach_price_history(pool, trading_date, sessions=5)
    foreign_map, foreign_errors = _load_foreign_net_map(trading_date)
    inst_map, inst_errors = load_inst_net_map(trading_date)

    dart_cache, news_cache, material = prefetch_dart_news(pool, trading_date)

    def _facts_for_row(row: dict[str, Any]) -> dict[str, Any]:
        t = str(row.get("ticker", "")).zfill(6)
        return build_fact_package(
            row,
            trading_date,
            dart_items=dart_cache.get(t) or fetch_dart_as_of(t, trading_date, max_items=3),
            news_items=news_cache.get(t) or fetch_news_as_of(t, str(row.get("name") or t), trading_date, max_items=5),
            foreign_map=foreign_map,
            inst_map=inst_map,
            foreign_errors=foreign_errors + inst_errors,
        )

    scouts_raw = {
        "A": scout_team_a(pool),
        "B": scout_team_b(pool, material_tickers=material),
        "C": scout_team_c(
            pool,
            foreign_net_fetcher=lambda t: foreign_map.get(str(t).zfill(6)),
        ),
        "D": scout_team_d(pool, actionable_events=[]),
    }

    team_inputs: dict[str, list[dict[str, Any]]] = {}
    row_by_ticker = {str(r.get("ticker", "")).zfill(6): r for r in pool}

    for tid, candidates in scouts_raw.items():
        limit = MAX_CANDIDATES[tid]
        packages: list[dict[str, Any]] = []
        for c in candidates[:limit]:
            row = row_by_ticker.get(c.ticker) or {"ticker": c.ticker, "name": c.name}
            pkg = _facts_for_row(row)
            packages.append(
                {
                    "ticker": c.ticker,
                    "name": c.name,
                    "scout_score": c.score,
                    "scout_reason_label": c.reason_label,
                    "scout_metrics": c.metrics,
                    "evidence_id": f"scout:{tid}:{c.ticker}:{trading_date}",
                    "fact_package": pkg,
                }
            )
        if tid == "B":
            material_rows = sorted(
                [r for r in pool if str(r.get("ticker", "")).zfill(6) in material],
                key=lambda r: -len(dart_cache.get(str(r.get("ticker", "")).zfill(6), [])),
            )[: MAX_CANDIDATES["B"]]
            seen = {p["ticker"] for p in packages}
            for row in material_rows:
                t = str(row.get("ticker", "")).zfill(6)
                if t in seen:
                    continue
                if not (dart_cache.get(t) or news_cache.get(t)):
                    continue
                packages.append(
                    {
                        "ticker": t,
                        "name": row.get("name"),
                        "scout_score": 50.0,
                        "scout_reason_label": "material_linked",
                        "scout_metrics": {},
                        "evidence_id": f"scout:B:{t}:{trading_date}",
                        "fact_package": _facts_for_row(row),
                    }
                )
                seen.add(t)
                if len(packages) >= MAX_CANDIDATES["B"]:
                    break
        team_inputs[tid] = packages[:limit]

    meta = {
        "material_tickers": sorted(material),
        "foreign_net_tickers": len(foreign_map),
        "inst_net_tickers": len(inst_map),
        "dart_prefetch_n": DART_PREFETCH_TOP_N,
        "foreign_errors": foreign_errors[:5],
        "inst_errors": inst_errors[:5],
    }
    return team_inputs, meta
