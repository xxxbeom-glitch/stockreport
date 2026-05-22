# -*- coding: utf-8 -*-
"""mock_trading: KIS 현재가 → 코스닥·59,000원 이하만 holdings, 나머지 excluded_candidates."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.api_env import ensure_env_loaded
from data.kis_client import get_price as get_kis_price

try:
    from agents.weekly_watchlist_update.weekly_metrics import resolve_pykrx_market
except Exception:
    resolve_pykrx_market = None  # type: ignore

import config

DATA_PATH = ROOT / "data" / "mock_trading" / "trading_data.json"
KST = ZoneInfo("Asia/Seoul")
MAX_DISPLAY_PRICE = 59_000

_CANDIDATE_STATIC_KEYS = (
    "ticker",
    "name",
    "sector",
    "business_summary",
    "buy_amount",
    "agent",
    "status",
    "selection_reason",
)


def _round_pct(value: float) -> float:
    return round(value, 2)


def _kis_ready() -> bool:
    return bool(config.KIS_APP_KEY and config.KIS_APP_SECRET)


def _fetch_kis_price(ticker: str) -> tuple[int | None, str | None]:
    """(current_price, error_message) — KIS만 사용."""
    code = str(ticker).zfill(6)
    try:
        quote = get_kis_price(code)
    except Exception as exc:
        return None, f"KIS 조회 예외: {type(exc).__name__}"

    if not quote:
        return None, "KIS 시세 응답 없음"

    price = quote.get("price")
    if price is None:
        return None, "KIS 응답에 가격 없음"

    try:
        current = int(round(float(price)))
    except (TypeError, ValueError):
        return None, "가격 파싱 실패"

    if current <= 0:
        return None, "유효하지 않은 가격(0 이하)"

    return current, None


def _resolve_market(ticker: str) -> dict[str, Any]:
    """pykrx 목록 기반 시장 판별 (기존 weekly_metrics 로직 재사용)."""
    code = str(ticker).zfill(6)
    if resolve_pykrx_market is None:
        return {
            "market_check_status": "unverified",
            "resolved_market": None,
            "resolve_source": "pykrx_unavailable",
        }

    try:
        info = resolve_pykrx_market(code)
    except Exception as exc:
        return {
            "market_check_status": "unverified",
            "resolved_market": None,
            "resolve_source": f"resolve_error:{type(exc).__name__}",
        }

    resolved = info.get("resolved_market")
    source = info.get("resolve_source") or ""
    if resolved in ("KOSPI", "KOSDAQ", "KONEX"):
        return {
            "market_check_status": "verified",
            "resolved_market": resolved,
            "resolve_source": source,
            "in_kospi": info.get("in_kospi"),
            "in_kosdaq": info.get("in_kosdaq"),
        }

    return {
        "market_check_status": "unverified",
        "resolved_market": resolved,
        "resolve_source": source or "unknown",
    }


def _enrich_candidate(row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """KIS 가격·시장 메타 반영한 스냅샷 (holdings/excluded 공통)."""
    out = dict(row)
    ticker = str(out.get("ticker") or "").zfill(6)
    out["ticker"] = ticker

    buy = out.get("buy_amount")
    try:
        buy_int = int(round(float(buy)))
    except (TypeError, ValueError):
        buy_int = 0
    out["buy_price"] = buy_int

    market_meta = _resolve_market(ticker)
    out.update(market_meta)

    current, err = _fetch_kis_price(ticker)
    if err:
        out["price_status"] = "error"
        out["price_error"] = err
        out["price_source"] = None
        for key in ("current_price", "eval_amount", "return_pct", "price_updated_at"):
            out.pop(key, None)
        return out

    assert current is not None
    out["current_price"] = current
    out["eval_amount"] = current
    out["price_source"] = "kis"
    out["price_updated_at"] = now.isoformat(timespec="seconds")
    out["price_status"] = "ok"
    out.pop("price_error", None)

    if buy_int > 0:
        out["return_pct"] = _round_pct((current - buy_int) / buy_int * 100.0)
    else:
        out["return_pct"] = None

    return out


def _exclusion_reason(row: dict[str, Any]) -> str | None:
    if row.get("price_status") == "error":
        return str(row.get("price_error") or "시세 조회 실패")

    if row.get("price_status") != "ok":
        return "시세 미확정"

    current = int(row.get("current_price") or 0)
    if current > MAX_DISPLAY_PRICE:
        return f"현재가 {current:,}원 > 한도 {MAX_DISPLAY_PRICE:,}원"

    if row.get("market_check_status") == "verified":
        if row.get("resolved_market") != "KOSDAQ":
            market = row.get("resolved_market") or "알 수 없음"
            return f"코스닥 아님 ({market})"

    return None


def _static_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in _CANDIDATE_STATIC_KEYS if k in row}


def _load_source_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """재실행 시에도 6개 후보 전체를 다시 조회."""
    if payload.get("candidates"):
        return [dict(r) for r in payload["candidates"]]

    by_ticker: dict[str, dict[str, Any]] = {}
    for row in list(payload.get("holdings") or []) + list(
        payload.get("excluded_candidates") or []
    ):
        t = str(row.get("ticker") or "").zfill(6)
        if t:
            by_ticker[t] = _static_row(row)
    return list(by_ticker.values())


def _split_holdings(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    holdings: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for row in rows:
        reason = _exclusion_reason(row)
        if reason:
            ex = dict(row)
            ex["exclude_reason"] = reason
            excluded.append(ex)
        else:
            holdings.append(row)

    return holdings, excluded


def _build_rankings(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for h in holdings:
        if h.get("price_status") != "ok":
            continue
        buy = h.get("buy_price") or h.get("buy_amount")
        pct = h.get("return_pct")
        rows.append(
            {
                "name": h.get("name"),
                "buy_amount": buy,
                "eval_amount": h.get("eval_amount"),
                "return_pct": pct,
                "return_pct_rank": int(round(float(pct))) if pct is not None else None,
            }
        )
    rows.sort(key=lambda r: float(r.get("return_pct") or 0.0), reverse=True)
    return rows


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ensure_env_loaded()

    if not _kis_ready():
        print("실패: KIS API 자격증명 미설정 (KIS_APP_KEY / KIS_APP_SECRET)")
        return 1

    if not DATA_PATH.is_file():
        print(f"실패: {DATA_PATH} 없음")
        return 1

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    source_rows = _load_source_rows(payload)
    if not source_rows:
        print("실패: candidates/holdings 후보 비어 있음")
        return 1

    now = datetime.now(KST)
    enriched = [_enrich_candidate(dict(row), now=now) for row in source_rows]
    holdings, excluded = _split_holdings(enriched)

    payload["candidates"] = [_static_row(row) for row in source_rows]

    meta = payload.setdefault("pageMeta", {})
    meta["updated_at"] = now.strftime("%H:%M 업데이트")
    meta["price_refreshed_at"] = now.isoformat(timespec="seconds")
    meta["max_display_price"] = MAX_DISPLAY_PRICE
    meta["display_market"] = "KOSDAQ"

    payload["holdings"] = holdings
    payload["excluded_candidates"] = excluded
    payload["rankings"] = _build_rankings(holdings)

    DATA_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    unverified = [r for r in enriched if r.get("market_check_status") == "unverified"]

    print(f"조회 완료 (KIS, 한도 {MAX_DISPLAY_PRICE:,}원, 코스닥 verified 시만 시장 필터)")
    print(f" - 표시 holdings: {len(holdings)}종")
    for h in holdings:
        print(
            f"   · {h.get('name')}: {int(h['current_price']):,}원, "
            f"상세 수익률 {float(h['return_pct']):+.2f}%"
        )

    if excluded:
        print(f" - 제외 excluded_candidates: {len(excluded)}종")
        for ex in excluded:
            price = ex.get("current_price")
            price_s = f"{int(price):,}원" if price is not None else "—"
            print(f"   · {ex.get('name')}: {price_s} — {ex.get('exclude_reason')}")

    if unverified:
        print(f" - 시장 미확인(unverified): {len(unverified)}종 (임의 코스닥 판정 없음)")
        for u in unverified:
            print(
                f"   · {u.get('name')}({u.get('ticker')}): "
                f"source={u.get('resolve_source')}"
            )

    print(f" - 갱신 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} KST")

    if not holdings:
        print("경고: 화면 표시 종목 없음")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
