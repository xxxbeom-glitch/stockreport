"""Signal detection from DART, news, KIS/pykrx market data."""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Callable, Optional

from src.trading.competition.events.models import EvidenceRef, RawSignal
from src.trading.competition.universe.filters import assess_kis_risk

logger = logging.getLogger(__name__)

# Thresholds
PRICE_SPIKE_PCT = 5.0
PRICE_DROP_PCT = -5.0
TV_RATIO_MIN = 2.0
FOREIGN_NET_MIN_EOK = 30  # 억 원 scale hint

DART_POSITIVE_KEYWORDS = (
    "단일판매",
    "공급계약",
    "신규시설투자",
    "잠정실적",
    "실적",
    "흑자전환",
)
DART_NEGATIVE_KEYWORDS = (
    "소송",
    "피소",
    "손실",
    "적자",
    "하향",
)
DART_RISK_KEYWORDS = (
    "거래정지",
    "관리종목",
    "정리매매",
    "상장폐지",
    "유상증자",
    "감사의견",
    "부적정",
    "의견거절",
)

NEWS_RISK_KEYWORDS = (
    "거래정지",
    "관리종목",
    "상장폐지",
    "횡령",
    "분식회계",
    "조사",
    "압수수색",
)


def _signal_id() -> str:
    return uuid.uuid4().hex[:16]


def _classify_dart(report_nm: str) -> str | None:
    name = str(report_nm or "")
    if not name:
        return None
    for kw in DART_RISK_KEYWORDS:
        if kw in name:
            return "DISCLOSURE_RISK"
    for kw in DART_NEGATIVE_KEYWORDS:
        if kw in name:
            return "DISCLOSURE_NEGATIVE"
    for kw in DART_POSITIVE_KEYWORDS:
        if kw in name:
            return "DISCLOSURE_POSITIVE"
    return None


def detect_dart_signals(
    ticker: str,
    name: str,
    *,
    scope: str,
    holding_teams: list[str] | None = None,
    days: int = 3,
    fetcher: Callable[..., list[dict[str, Any]]] | None = None,
) -> list[RawSignal]:
    holding_teams = holding_teams or []
    out: list[RawSignal] = []
    try:
        from data.dart_client import fetch_disclosure_items

        fetch = fetcher or fetch_disclosure_items
        items = fetch(ticker, days=days, max_items=20)
    except Exception as exc:
        logger.debug("DART skip %s: %s", ticker, exc)
        return out

    for item in items or []:
        report_nm = str(item.get("report_nm") or "")
        rcept_no = str(item.get("rcept_no") or "").strip()
        if not rcept_no:
            continue
        event_type = _classify_dart(report_nm)
        if not event_type:
            continue
        direction = "UNKNOWN"
        if event_type == "DISCLOSURE_POSITIVE":
            direction = "POSITIVE"
        elif event_type in ("DISCLOSURE_NEGATIVE", "DISCLOSURE_RISK"):
            direction = "NEGATIVE"
        importance = "HIGH" if event_type == "DISCLOSURE_RISK" else "MEDIUM"
        if scope == "position_holding" and event_type == "DISCLOSURE_RISK":
            importance = "CRITICAL"

        out.append(
            RawSignal(
                signal_id=_signal_id(),
                ticker=ticker.zfill(6),
                name=name,
                event_type=event_type,  # type: ignore[arg-type]
                scope=scope,  # type: ignore[arg-type]
                summary=f"DART: {report_nm[:120]}",
                evidence=EvidenceRef(
                    evidence_id=f"dart:{rcept_no}",
                    source_type="dart",
                    title=report_nm,
                    published_at=str(item.get("rcept_dt") or ""),
                    raw=item,
                ),
                importance_hint=importance,  # type: ignore[arg-type]
                direction_hint=direction,  # type: ignore[arg-type]
                holding_teams=holding_teams,
            )
        )
    return out


def detect_news_signals(
    ticker: str,
    name: str,
    *,
    scope: str,
    holding_teams: list[str] | None = None,
    search_fn: Callable[..., list[dict[str, Any]]] | None = None,
) -> list[RawSignal]:
    holding_teams = holding_teams or []
    out: list[RawSignal] = []
    query = name if name and name != ticker else ticker
    try:
        from data.naver_news_client import search_stock_news

        search = search_fn or search_stock_news
        items = search(query, display=3, sort="date")
    except Exception as exc:
        logger.debug("News skip %s: %s", ticker, exc)
        return out

    for item in items or []:
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or item.get("originallink") or "").strip()
        if not title:
            continue
        pub = str(item.get("pub_date") or "")
        evidence_id = f"news:{hashlib.sha256((link or title).encode()).hexdigest()[:24]}"

        event_type = "NEWS_MATERIAL"
        direction: str = "UNKNOWN"
        importance: str = "MEDIUM"
        for kw in NEWS_RISK_KEYWORDS:
            if kw in title:
                direction = "NEGATIVE"
                importance = "HIGH" if scope == "position_holding" else "MEDIUM"
                break

        if scope == "position_holding" and direction == "NEGATIVE":
            importance = "CRITICAL"

        out.append(
            RawSignal(
                signal_id=_signal_id(),
                ticker=ticker.zfill(6),
                name=name,
                event_type=event_type,  # type: ignore[arg-type]
                scope=scope,  # type: ignore[arg-type]
                summary=f"뉴스: {title[:120]}",
                evidence=EvidenceRef(
                    evidence_id=evidence_id,
                    source_type="naver_news",
                    title=title,
                    url=link,
                    published_at=pub,
                    raw=item,
                ),
                importance_hint=importance,  # type: ignore[arg-type]
                direction_hint=direction,  # type: ignore[arg-type]
                holding_teams=holding_teams,
            )
        )
    return out


def detect_price_volume_signals(
    ticker: str,
    name: str,
    *,
    scope: str,
    holding_teams: list[str] | None = None,
    quote: dict[str, Any] | None = None,
    tv_ratio_20d: Optional[float] = None,
) -> list[RawSignal]:
    holding_teams = holding_teams or []
    out: list[RawSignal] = []

    if quote is None:
        try:
            from data.kis_client import get_price

            quote = get_price(ticker.zfill(6))
        except Exception:
            quote = None

    if not quote:
        return out

    raw = quote.get("raw") or {}
    change_rate = float(quote.get("change_rate") or raw.get("prdy_ctrt") or 0)
    price = int(float(quote.get("price") or raw.get("stck_prpr") or 0))
    if price <= 0:
        return out

    evidence_base = f"kis:{ticker.zfill(6)}:{raw.get('stck_cntg_hour', 'session')}"

    if change_rate >= PRICE_SPIKE_PCT or change_rate <= PRICE_DROP_PCT:
        direction = "POSITIVE" if change_rate > 0 else "NEGATIVE"
        importance: str = "HIGH" if abs(change_rate) >= 10 else "MEDIUM"
        if scope == "position_holding" and change_rate <= PRICE_DROP_PCT:
            importance = "CRITICAL"
        out.append(
            RawSignal(
                signal_id=_signal_id(),
                ticker=ticker.zfill(6),
                name=name,
                event_type="PRICE_VOLUME_ANOMALY",
                scope=scope,  # type: ignore[arg-type]
                summary=f"가격 이상: {change_rate:+.2f}% (현재 {price:,}원)",
                evidence=EvidenceRef(
                    evidence_id=f"{evidence_base}:price",
                    source_type="kis",
                    title=f"price_change_{change_rate:.2f}",
                    raw={"change_rate": change_rate, "price": price},
                ),
                importance_hint=importance,  # type: ignore[arg-type]
                direction_hint=direction,  # type: ignore[arg-type]
                holding_teams=holding_teams,
                metrics={"change_rate_pct": change_rate, "price": price},
            )
        )

    if tv_ratio_20d is not None and tv_ratio_20d >= TV_RATIO_MIN:
        out.append(
            RawSignal(
                signal_id=_signal_id(),
                ticker=ticker.zfill(6),
                name=name,
                event_type="PRICE_VOLUME_ANOMALY",
                scope=scope,  # type: ignore[arg-type]
                summary=f"거래대금 급증: 20일 대비 {tv_ratio_20d:.1f}배",
                evidence=EvidenceRef(
                    evidence_id=f"{evidence_base}:tv_ratio",
                    source_type="kis",
                    title=f"tv_ratio_{tv_ratio_20d:.2f}",
                    raw={"tv_ratio_20d": tv_ratio_20d},
                ),
                importance_hint="MEDIUM",
                direction_hint="UNKNOWN",
                holding_teams=holding_teams,
                metrics={"tv_ratio_20d": tv_ratio_20d},
            )
        )

    return out


def detect_supply_signals(
    ticker: str,
    name: str,
    *,
    scope: str,
    holding_teams: list[str] | None = None,
    foreign_net: float | None = None,
) -> list[RawSignal]:
    holding_teams = holding_teams or []
    if foreign_net is None:
        try:
            from data.kr_market import get_foreign_net_by_ticker

            foreign_net = get_foreign_net_by_ticker(ticker.zfill(6))
        except Exception:
            foreign_net = None

    if foreign_net is None:
        return []

    eok = abs(foreign_net) / 100_000_000
    if eok < FOREIGN_NET_MIN_EOK:
        return []

    direction = "POSITIVE" if foreign_net > 0 else "NEGATIVE"
    return [
        RawSignal(
            signal_id=_signal_id(),
            ticker=ticker.zfill(6),
            name=name,
            event_type="SUPPLY_DEMAND_SHIFT",
            scope=scope,  # type: ignore[arg-type]
            summary=f"외국인 수급 변화: {foreign_net/100_000_000:+.0f}억원",
            evidence=EvidenceRef(
                evidence_id=f"supply:{ticker.zfill(6)}:foreign",
                source_type="kis",
                title="foreign_net_flow",
                raw={"foreign_net": foreign_net},
            ),
            importance_hint="MEDIUM",
            direction_hint=direction,  # type: ignore[arg-type]
            holding_teams=holding_teams,
            metrics={"foreign_net": foreign_net},
        )
    ]


def detect_position_risk_signals(
    ticker: str,
    name: str,
    *,
    holding_teams: list[str],
    quote: dict[str, Any] | None = None,
) -> list[RawSignal]:
    """Position-only: KIS risk flags and trading status."""
    if not holding_teams:
        return []

    if quote is None:
        try:
            from data.kis_client import get_price

            quote = get_price(ticker.zfill(6))
        except Exception:
            quote = None

    raw = (quote or {}).get("raw") or {}
    risk = assess_kis_risk(raw if isinstance(raw, dict) else None)
    out: list[RawSignal] = []

    if risk.get("exclude_new_entry") or risk.get("risk_status") not in (
        "normal",
        None,
    ):
        status = risk.get("risk_status", "unknown")
        notes = ", ".join(risk.get("notes") or [])
        out.append(
            RawSignal(
                signal_id=_signal_id(),
                ticker=ticker.zfill(6),
                name=name,
                event_type="POSITION_RISK_ALERT",
                scope="position_holding",
                summary=f"보유종목 위험: {notes or status}",
                evidence=EvidenceRef(
                    evidence_id=f"risk:{ticker.zfill(6)}:{status}",
                    source_type="kis",
                    title=notes or status,
                    raw=dict(risk),
                ),
                importance_hint="CRITICAL",
                direction_hint="NEGATIVE",
                holding_teams=list(holding_teams),
            )
        )
        out.append(
            RawSignal(
                signal_id=_signal_id(),
                ticker=ticker.zfill(6),
                name=name,
                event_type="TRADING_STATUS_CHANGE",
                scope="position_holding",
                summary=f"거래상태 변경: {notes or status}",
                evidence=EvidenceRef(
                    evidence_id=f"trading_status:{ticker.zfill(6)}:{status}",
                    source_type="kis",
                    title=notes or status,
                    raw=dict(risk),
                ),
                importance_hint="CRITICAL",
                direction_hint="NEGATIVE",
                holding_teams=list(holding_teams),
            )
        )

    return out


def scan_ticker(
    ticker: str,
    name: str,
    *,
    scope: str,
    holding_teams: list[str] | None = None,
    include_dart: bool = True,
    include_news: bool = True,
    include_market: bool = True,
    stock_meta: dict[str, Any] | None = None,
) -> list[RawSignal]:
    """Run all detectors for one ticker in given scope."""
    holding_teams = holding_teams or []
    meta = stock_meta or {}
    tv_ratio: float | None = None
    avg_tv = meta.get("avg_trading_value_20d_krw")
    cur_tv = meta.get("current_trading_value_krw")
    if avg_tv and cur_tv and avg_tv > 0:
        tv_ratio = float(cur_tv) / float(avg_tv)

    signals: list[RawSignal] = []

    if include_dart:
        signals.extend(
            detect_dart_signals(
                ticker, name, scope=scope, holding_teams=holding_teams
            )
        )
    if include_news:
        signals.extend(
            detect_news_signals(
                ticker, name, scope=scope, holding_teams=holding_teams
            )
        )
    if include_market:
        signals.extend(
            detect_price_volume_signals(
                ticker,
                name,
                scope=scope,
                holding_teams=holding_teams,
                tv_ratio_20d=tv_ratio,
            )
        )
        if scope == "eligible_candidate":
            signals.extend(
                detect_supply_signals(
                    ticker, name, scope=scope, holding_teams=holding_teams
                )
            )

    if scope == "position_holding" and holding_teams:
        signals.extend(
            detect_position_risk_signals(ticker, name, holding_teams=holding_teams)
        )

    if tv_ratio is not None:
        for sig in signals:
            sig.metrics.setdefault("tv_ratio_20d", tv_ratio)

    return signals
