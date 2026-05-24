"""One-time historical seed run — real market data, no live orders."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.trading.competition.bootstrap import bootstrap_competition
from src.trading.competition.constants import INITIAL_CASH_KRW, MAX_CANDIDATES, TEAM_IDS
from src.trading.competition.decision.models import DecisionTrigger, StrategyCandidate
from src.trading.competition.decision.strategy_scouts import (
    A_MIN_CHANGE_PCT,
    A_MIN_TV_RATIO,
    C_MIN_AVG_TV,
    scout_team_a,
    scout_team_b,
    scout_team_d,
)
from src.trading.competition.execution.accounting import capture_team_snapshots
from src.trading.competition.execution.executor import execute_decision
from src.trading.competition.execution.market_session import SessionContext, SessionKind
from src.trading.competition.execution.validator import validate_order_proposal
from src.trading.competition.storage.accounts import load_all_accounts, load_account
from src.trading.competition.storage.config_store import load_config, save_config
from src.trading.competition.storage.journal import append_notification
from src.trading.competition.teams.pipeline import run_decisions_for_triggers
from src.trading.competition.universe.builder import UNIVERSE_DIR, build_universe, load_eligible_universe

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[3]

DEFAULT_AS_OF = "20260522"
DEFAULT_AS_OF_ISO = "2026-05-22"
SEED_CLOSE_TS = f"{DEFAULT_AS_OF_ISO}T15:30:00+09:00"

SEED_EXECUTION_META = {
    "execution_mode": "historical_seed",
    "as_of_date": DEFAULT_AS_OF_ISO,
    "reset_required_before_live": True,
    "run_purpose": "ui_storage_flow_verification",
    "price_source": "pykrx_close",
    "fees_applied": False,
}


def as_of_display(trading_date: str) -> str:
    if len(trading_date) == 8:
        return f"{trading_date[:4]}-{trading_date[4:6]}-{trading_date[6:8]}"
    return trading_date


def seed_session_id(trading_date: str) -> str:
    return f"seed_{trading_date}_close"


def seed_close_timestamp(trading_date: str) -> str:
    return f"{as_of_display(trading_date)}T15:30:00+09:00"


def seed_execution_meta(trading_date: str) -> dict[str, Any]:
    return {
        **SEED_EXECUTION_META,
        "as_of_date": as_of_display(trading_date),
        "trading_date": trading_date,
    }


@contextmanager
def seed_timestamps(trading_date: str):
    ts = seed_close_timestamp(trading_date)

    def _fixed_now() -> str:
        return ts

    patches = [
        patch("src.trading.competition.teams.engine.now_kst_iso", _fixed_now),
        patch("src.trading.competition.teams.mock_provider.now_kst_iso", _fixed_now),
        patch("src.trading.competition.models.now_kst_iso", _fixed_now),
        patch("src.trading.competition.execution.executor.now_kst_iso", _fixed_now),
        patch("src.trading.competition.execution.accounting.now_kst_iso", _fixed_now),
    ]
    for p in patches:
        p.start()
    try:
        yield ts
    finally:
        for p in patches:
            p.stop()


def ensure_universe(trading_date: str, *, skip_kis_risk: bool = False) -> dict[str, Any]:
    summary_path = UNIVERSE_DIR / "build_summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("trading_date") == trading_date and summary.get("eligible_count", 0) > 0:
            return {"ok": True, "action": "reused", "summary": summary}

    result = build_universe(
        trading_date,
        enrich_kis_risk=not skip_kis_risk,
        kis_workers=8,
    )
    return {"ok": True, "action": "built", "summary": result}


def _pykrx_stock() -> Any | None:
    try:
        from pykrx import stock as pykrx_stock  # type: ignore

        return pykrx_stock
    except Exception:
        return None


def _replay_prev_trading_date(trading_date: str) -> str | None:
    from datetime import datetime, timedelta

    from src.trading.competition.replay.data_provider import list_trading_dates_result

    start = (datetime.strptime(trading_date, "%Y%m%d") - timedelta(days=30)).strftime("%Y%m%d")
    cal = list_trading_dates_result(start, trading_date)
    dates = cal.get("dates") or []
    if len(dates) >= 2:
        return dates[-2]
    return None


def enrich_universe_historical(
    stocks: list[dict[str, Any]],
    trading_date: str,
) -> dict[str, Any]:
    """Attach change_rate_pct and tv_ratio for trading_date (KIS-first when KIS keys present)."""
    from src.trading.competition.replay.data_provider import _kis_ready, enrich_universe_rows_kis
    from src.trading.competition.replay.pykrx_safe import krx_credentials_configured, safe_pykrx_call
    from src.trading.competition.universe.collector import recent_trading_dates

    provider_attempts: list[dict[str, Any]] = []
    errors: list[str] = []

    if not stocks:
        return {
            "ok": False,
            "error": "eligible_universe_empty",
            "failures": [],
            "errors": errors,
            "provider_attempts": provider_attempts,
        }

    min_enriched = max(10, len(stocks) // 100)
    kis_out: dict[str, Any] = {}

    if _kis_ready():
        prev_date = _replay_prev_trading_date(trading_date)
        kis_out = enrich_universe_rows_kis(stocks, trading_date, prev_date)
        provider_attempts.append(
            {
                "provider": "kis_per_ticker",
                "ok": bool(kis_out.get("ok")),
                "enriched": kis_out.get("enriched"),
                "primary_source": kis_out.get("source"),
            }
        )
        if int(kis_out.get("enriched") or 0) >= min_enriched:
            kis_out["provider_attempts"] = provider_attempts
            kis_out.setdefault("primary_source", "kis_per_ticker")
            return kis_out
        errors.extend(kis_out.get("errors") or [])
        errors.append(f"kis:insufficient_enriched:{kis_out.get('enriched')}/{len(stocks)}")

    if not krx_credentials_configured():
        return {
            "ok": False,
            "error": "market_data_unavailable",
            "detail": "KIS historical OHLCV insufficient and KRX_ID/KRX_PW not set for pykrx fallback",
            "failures": kis_out.get("failures", []) if _kis_ready() else [],
            "errors": errors,
            "provider_attempts": provider_attempts,
            "krx_login_required": not _kis_ready(),
            "kis_configured": _kis_ready(),
        }

    pykrx = _pykrx_stock()
    if pykrx is None:
        return {
            "ok": False,
            "error": "pykrx_unavailable",
            "failures": [],
            "errors": errors,
            "provider_attempts": provider_attempts,
        }

    dates = recent_trading_dates(trading_date, 2, pykrx=pykrx)
    if trading_date not in dates:
        dates.append(trading_date)
    dates = sorted(set(dates))
    prev_date = dates[-2] if len(dates) >= 2 else None

    ohlcv: dict[str, dict[str, dict[str, int]]] = {}
    for date in dates[-2:]:
        ohlcv[date] = {}
        for market in ("KOSPI", "KOSDAQ"):
            frame, meta = safe_pykrx_call(
                f"get_market_ohlcv:{market}:{date}",
                lambda d=date, m=market: pykrx.get_market_ohlcv(d, market=m),
            )
            provider_attempts.append(meta)
            if not meta.get("ok"):
                errors.append(f"{market}/{date}:{meta.get('error_code')}")
                continue
            for ticker, row in frame.iterrows():
                code = str(ticker).zfill(6)
                try:
                    close = int(float(row.get("종가", 0) or 0))
                    tv = int(float(row.get("거래대금", 0) or 0))
                except (TypeError, ValueError):
                    continue
                ohlcv[date][code] = {"close": close, "tv": tv}

    bulk_missing = not ohlcv.get(trading_date)
    if bulk_missing and stocks and _kis_ready():
        prev_date = _replay_prev_trading_date(trading_date)
        kis_out = enrich_universe_rows_kis(stocks, trading_date, prev_date)
        kis_out["errors"] = errors + (kis_out.get("errors") or [])
        kis_out["provider_attempts"] = provider_attempts + [
            {"provider": "kis_per_ticker_fallback", "ok": bool(kis_out.get("ok"))}
        ]
        if int(kis_out.get("enriched") or 0) >= min_enriched:
            return kis_out
        return {
            "ok": False,
            "error": "market_data_unavailable",
            "detail": "pykrx bulk empty and KIS per-ticker enrich insufficient",
            "enriched": kis_out.get("enriched"),
            "failures": kis_out.get("failures") or [],
            "errors": errors + (kis_out.get("errors") or []),
            "provider_attempts": provider_attempts,
        }

    failures: list[dict[str, str]] = []
    enriched = 0
    for row in stocks:
        ticker = str(row.get("ticker", "")).zfill(6)
        day = ohlcv.get(trading_date, {}).get(ticker)
        if not day or day["close"] <= 0:
            failures.append({"ticker": ticker, "reason": "ohlcv_missing_on_as_of_date"})
            continue
        row["current_price_krw"] = day["close"]
        row["current_trading_value_krw"] = day["tv"]
        avg_tv = float(row.get("avg_trading_value_20d_krw") or 0)
        if avg_tv > 0 and day["tv"] > 0:
            row["tv_ratio_20d"] = day["tv"] / avg_tv
        if prev_date:
            prev = ohlcv.get(prev_date, {}).get(ticker)
            if prev and prev["close"] > 0:
                row["change_rate_pct"] = (day["close"] - prev["close"]) / prev["close"] * 100
        row.setdefault("data_sources", [])
        if "pykrx_historical" not in row["data_sources"]:
            row["data_sources"].append("pykrx_historical")
        enriched += 1

    ok = enriched >= min_enriched
    return {
        "ok": ok,
        "error": None if ok else "insufficient_priced_universe",
        "enriched": enriched,
        "failures": failures,
        "errors": errors,
        "prev_trading_date": prev_date,
        "provider_attempts": provider_attempts,
        "primary_source": "pykrx_bulk",
    }


def _load_foreign_net_map(trading_date: str) -> tuple[dict[str, float], list[str]]:
    from data.kr_market import _fetch_foreign_net_purchases_frame

    cache: dict[str, float] = {}
    errors: list[str] = []
    for market in ("KOSPI", "KOSDAQ"):
        frame = _fetch_foreign_net_purchases_frame(market, date=trading_date)
        if frame is None:
            errors.append(f"foreign_net_unavailable:{market}")
            continue
        for ticker, row in frame.iterrows():
            code = str(ticker).zfill(6)
            try:
                val = float(row.iloc[-1])
            except (TypeError, ValueError, IndexError):
                continue
            cache[code] = val
    return cache, errors


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = row.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def scout_team_c_historical(
    stocks: list[dict[str, Any]],
    *,
    foreign_map: dict[str, float],
    foreign_errors: list[str],
) -> list[StrategyCandidate]:
    pool = sorted(stocks, key=lambda r: _f(r, "avg_trading_value_20d_krw"), reverse=True)[:80]
    scored: list[StrategyCandidate] = []
    for row in pool:
        ticker = str(row.get("ticker", "")).zfill(6)
        avg_tv = _f(row, "avg_trading_value_20d_krw")
        if avg_tv < C_MIN_AVG_TV:
            continue
        foreign = foreign_map.get(ticker)
        score = avg_tv / 1_000_000_000
        metrics: dict[str, Any] = {
            "avg_trading_value_20d_krw": int(avg_tv),
            "foreign_net": foreign,
            "foreign_net_status": "available" if foreign is not None else "unavailable",
        }
        if foreign is not None:
            score += foreign / 100_000_000
        scored.append(
            StrategyCandidate(
                ticker=ticker,
                name=str(row.get("name") or ticker),
                score=score,
                reason_label="supply_persistence" if foreign is not None else "liquidity_only_no_foreign_data",
                metrics=metrics,
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[: MAX_CANDIDATES["C"]]


def scout_teams_historical(
    universe: list[dict[str, Any]],
    trading_date: str,
) -> tuple[dict[str, list[StrategyCandidate]], dict[str, Any]]:
    foreign_map, foreign_errors = _load_foreign_net_map(trading_date)
    material_tickers: set[str] = set()
    material_note = (
        "historical_disclosure_news_not_replayed_for_seed_run; "
        "team_b_uses_liquidity_candidates_only"
    )

    scouts = {
        "A": scout_team_a(universe),
        "B": scout_team_b(universe, material_tickers=material_tickers),
        "C": scout_team_c_historical(universe, foreign_map=foreign_map, foreign_errors=foreign_errors),
        "D": scout_team_d(universe, actionable_events=[]),
    }
    meta = {
        "material_tickers_count": 0,
        "material_note": material_note,
        "foreign_net_errors": foreign_errors,
        "foreign_net_tickers": len(foreign_map),
        "scout_thresholds": {
            "A": {"min_tv_ratio": A_MIN_TV_RATIO, "min_change_pct": A_MIN_CHANGE_PCT},
            "C": {"min_avg_tv": C_MIN_AVG_TV},
        },
    }
    return scouts, meta


def _candidate_dict(c: StrategyCandidate, *, team_id: str, trading_date: str) -> dict[str, Any]:
    d = c.to_dict()
    d["evidence_ids"] = [f"scout:{team_id}:{c.ticker}:{trading_date}"]
    return d


def build_seed_triggers(
    session_id: str,
    scouts: dict[str, list[StrategyCandidate]],
    trading_date: str,
    universe_by_ticker: dict[str, dict[str, Any]],
) -> list[DecisionTrigger]:
    triggers: list[DecisionTrigger] = []
    for team_id in TEAM_IDS:
        cands = scouts.get(team_id) or []
        candidates = [_candidate_dict(c, team_id=team_id, trading_date=trading_date) for c in cands]
        for cand in candidates:
            row = universe_by_ticker.get(str(cand.get("ticker", "")).zfill(6), {})
            metrics = cand.setdefault("metrics", {})
            if row.get("current_price_krw"):
                metrics["current_price_krw"] = row["current_price_krw"]
            if row.get("change_rate_pct") is not None:
                metrics["change_rate_pct"] = row["change_rate_pct"]
        triggers.append(
            DecisionTrigger(
                trigger_id=f"seed_{uuid.uuid4().hex[:12]}",
                trigger_type="STRATEGY_CANDIDATE_REVIEW",
                team_id=team_id,
                session_id=session_id,
                summary=f"팀 {team_id} seed 후보 {len(cands)}건 ({trading_date} 장 종료)",
                priority="normal",
                candidates=candidates,
                evidence_ids=[e for c in candidates for e in c.get("evidence_ids", [])],
                context={
                    "scout_mode": "historical_seed",
                    "trading_date": trading_date,
                    "session_tradable": True,
                    "candidate_count": len(cands),
                },
            )
        )
    return triggers


def historical_close_quote(
    ticker: str,
    universe_by_ticker: dict[str, dict[str, Any]],
    trading_date: str,
) -> dict[str, Any] | None:
    row = universe_by_ticker.get(ticker.zfill(6))
    if not row:
        return None
    price = row.get("current_price_krw")
    if not price or int(price) <= 0:
        return None
    p = int(price)
    return {
        "price": p,
        "ask_price": p,
        "bid_price": p,
        "available_qty": 999_999,
        "source": "pykrx_close",
        "as_of_date": as_of_display(trading_date),
    }


def _resolve_quantity(decision: dict[str, Any], price: int, cash: int) -> int:
    qty = int(decision.get("quantity") or 0)
    alloc = int(decision.get("allocation_krw") or 0)
    if qty <= 0 and alloc > 0 and price > 0:
        qty = max(1, alloc // price)
    if qty <= 0 and price > 0 and cash > 0:
        qty = max(1, min(cash // price, 10))
    return qty


def execute_seed_decisions(
    decisions_out: list[dict[str, Any]],
    *,
    session_id: str,
    trading_date: str,
    universe_by_ticker: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    seed_session = SessionContext(
        kind=SessionKind.REGULAR,
        tradable=True,
        allows_market=True,
        allows_limit=True,
        allows_nxt=False,
        label="historical_seed_regular_close",
    )
    meta = seed_execution_meta(trading_date)
    ts = seed_close_timestamp(trading_date)
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in decisions_out:
        decision = dict(item["decision"])
        review = item.get("review")
        action = decision.get("action")
        if action not in ("BUY", "ADD_BUY"):
            results.append(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": f"non_buy_action:{action}",
                    "team_id": decision.get("team_id"),
                    "decision_id": decision.get("decision_id"),
                }
            )
            continue

        ticker = str(decision.get("ticker") or "").zfill(6)
        quote = historical_close_quote(ticker, universe_by_ticker, trading_date)
        if not quote:
            results.append(
                {
                    "ok": False,
                    "blocked": True,
                    "reason": "historical_price_unavailable",
                    "team_id": decision.get("team_id"),
                    "ticker": ticker,
                }
            )
            continue

        price = int(quote["price"])
        team_id = str(decision.get("team_id") or "")
        account = load_account(team_id)
        cash = account.cash_krw if account else 0
        qty = _resolve_quantity(decision, price, cash)
        decision["quantity"] = qty
        decision["allocation_krw"] = qty * price
        decision["_fill_price"] = price
        decision["_name"] = next(
            (c.get("name") for c in (decision.get("_candidates") or []) if c.get("ticker") == ticker),
            universe_by_ticker.get(ticker, {}).get("name", ticker),
        )

        ok, reason = validate_order_proposal(
            decision,
            review,
            session_tradable=True,
            seen_idempotency=seen,
            session=seed_session,
            quote=quote,
        )
        if not ok:
            results.append(
                {
                    "ok": False,
                    "blocked": True,
                    "reason": reason,
                    "team_id": team_id,
                    "ticker": ticker,
                }
            )
            continue

        ex = execute_decision(
            decision,
            review,
            session_id=session_id,
            fill_price=float(price),
            order_status="filled",
            executed_at=ts,
            execution_meta=meta,
        )
        results.append(ex)

    return results


def build_seed_slack_summary(report: dict[str, Any]) -> str:
    lines = [
        "[AI 투자 경쟁앱] 실제 데이터 초기 모의운용 테스트 완료",
        f"기준일: {report.get('as_of_display')} 장 종료 데이터 (pykrx)",
        f"목적: {report.get('run_purpose')}",
        f"session_id: {report.get('session_id')}",
        "",
    ]
    for tid in TEAM_IDS:
        team = report.get("teams", {}).get(tid, {})
        buys = team.get("fills") or []
        if buys:
            names = ", ".join(
                f"{b.get('name')}({b.get('quantity')}주@{int(b.get('fill_price_krw', 0)):,}원)"
                for b in buys
            )
            lines.append(
                f"팀 {tid}: 매수 {len(buys)}건 — {names} | 현금 {team.get('cash_krw', 0):,}원 | "
                f"총자산 {team.get('total_assets_krw', 0):,}원"
            )
        else:
            lines.append(
                f"팀 {tid}: 매수 0건 ({team.get('action', 'HOLD/WAIT')}) | "
                f"현금 {team.get('cash_krw', 0):,}원 | 총자산 {team.get('total_assets_krw', 0):,}원"
            )
    lines.extend(
        [
            "",
            "⚠️ 이 기록은 테스트용 seed run이며 실제 live 시작 전 초기화 대상입니다.",
            "초기화: python scripts/reset_competition_seed.py --confirm",
        ]
    )
    return "\n".join(lines)


def send_seed_slack_summary(report: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    from scripts.test_competition_slack import build_slack_test_payload, classify_webhook_url, send_slack_test

    message = build_seed_slack_summary(report)
    if dry_run:
        return {"ok": True, "dry_run": True, "message": message}

    import os

    webhook = (
        os.getenv("COMPETITION_SLACK_WEBHOOK", "").strip()
        or os.getenv("SLACK_WEBHOOK_URL", "").strip()
    )
    if not webhook:
        return {"ok": False, "error": "no_webhook_configured", "message": message}

    payload = build_slack_test_payload()
    payload["text"] = message
    payload["blocks"] = [{"type": "section", "text": {"type": "mrkdwn", "text": message}}]
    kind = classify_webhook_url(webhook)
    if kind == "workflow_trigger":
        return {"ok": False, "error": "workflow_trigger_webhook", "message": message}

    import urllib.error
    import urllib.request

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook.strip(),
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            ok = 200 <= resp.status < 300 and raw == "ok"
            return {"ok": ok, "status": resp.status, "response_body": raw, "message": message}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}", "message": message}


def run_historical_seed(
    trading_date: str = DEFAULT_AS_OF,
    *,
    force_mock: bool = False,
    send_slack: bool = True,
    slack_dry_run: bool = False,
    skip_universe_build: bool = False,
) -> dict[str, Any]:
    session_id = seed_session_id(trading_date)
    report: dict[str, Any] = {
        "ok": False,
        "session_id": session_id,
        "trading_date": trading_date,
        "as_of_display": as_of_display(trading_date),
        "run_purpose": SEED_EXECUTION_META["run_purpose"],
        "data_sources": ["pykrx"],
        "failures": [],
        "warnings": [],
    }

    cfg = load_config()
    if cfg.seed_run.get("completed_at") and cfg.run_mode == "historical_seed":
        report["failures"].append(
            {
                "step": "preflight",
                "reason": "seed_already_completed",
                "hint": "python scripts/reset_competition_seed.py --confirm 후 재실행",
            }
        )
        return report

    if not skip_universe_build:
        uni_result = ensure_universe(trading_date)
        report["universe"] = uni_result
        if not uni_result.get("ok"):
            return report

    universe = load_eligible_universe()
    if not universe:
        report["failures"].append({"step": "universe", "reason": "empty_eligible_universe"})
        return report

    enrich = enrich_universe_historical(universe, trading_date)
    report["universe_enrich"] = enrich
    if not enrich.get("ok"):
        report["failures"].append({"step": "enrich", "reason": enrich.get("error")})
        return report

    bootstrap = bootstrap_competition()
    report["bootstrap"] = bootstrap
    if not bootstrap.get("ok"):
        return report

    scouts, scout_meta = scout_teams_historical(universe, trading_date)
    report["scouts"] = {tid: [c.to_dict() for c in scouts[tid]] for tid in TEAM_IDS}
    report["scout_meta"] = scout_meta

    universe_by_ticker = {str(r["ticker"]).zfill(6): r for r in universe}

    triggers = build_seed_triggers(session_id, scouts, trading_date, universe_by_ticker)
    report["trigger_count"] = len(triggers)

    with seed_timestamps(trading_date):
        decisions_out = run_decisions_for_triggers(triggers, force_mock=force_mock)
        executions = execute_seed_decisions(
            decisions_out,
            session_id=session_id,
            trading_date=trading_date,
            universe_by_ticker=universe_by_ticker,
        )
        snapshots = capture_team_snapshots()

    accounts = load_all_accounts()
    team_report: dict[str, Any] = {}
    for tid in TEAM_IDS:
        acc = accounts.get(tid)
        dec = next((d["decision"] for d in decisions_out if d["decision"].get("team_id") == tid), {})
        fills = [
            e["trade"]
            for e in executions
            if e.get("ok") and e.get("trade") and e["trade"].get("team_id") == tid
        ]
        team_report[tid] = {
            "action": dec.get("action"),
            "decision_id": dec.get("decision_id"),
            "reason_label": dec.get("reason_label"),
            "reason_detail": dec.get("reason_detail"),
            "target_price": dec.get("target_price"),
            "review_conditions": dec.get("review_conditions"),
            "evidence_ids": dec.get("evidence_ids"),
            "fills": fills,
            "cash_krw": acc.cash_krw if acc else INITIAL_CASH_KRW,
            "total_assets_krw": acc.total_assets_krw if acc else INITIAL_CASH_KRW,
        }

    report["teams"] = team_report
    report["decisions"] = [d["decision"] for d in decisions_out]
    report["executions"] = executions
    report["snapshots_captured"] = len(snapshots)
    report["filled_count"] = sum(1 for e in executions if e.get("ok") and e.get("trade"))
    report["blocked_count"] = sum(1 for e in executions if e.get("blocked"))

    ts = seed_close_timestamp(trading_date)
    cfg = load_config()
    cfg.run_mode = "historical_seed"
    cfg.seed_run = {
        **seed_execution_meta(trading_date),
        "session_id": session_id,
        "completed_at": ts,
        "initial_cash_krw": INITIAL_CASH_KRW,
        "data_sources": report["data_sources"],
        "scout_meta": scout_meta,
        "filled_count": report["filled_count"],
    }
    cfg_result = save_config(cfg)
    report["config_persist"] = cfg_result

    append_notification(
        {
            "notification_id": f"ntf_{uuid.uuid4().hex[:10]}",
            "category": "system",
            "title": "실제 데이터 seed run 완료",
            "sub": f"{as_of_display(trading_date)} 장 종료 기준 — live 전 초기화 필요",
            "team_id": None,
            "read": False,
            "created_at": ts,
            **seed_execution_meta(trading_date),
        }
    )

    if send_slack:
        report["slack"] = send_seed_slack_summary(report, dry_run=slack_dry_run)

    from src.trading.competition.dashboard.payload import build_dashboard_payload

    report["dashboard_preview"] = {
        "asset_total": build_dashboard_payload().get("assetTotalKrw"),
        "trade_count": len(build_dashboard_payload().get("tradeHistory", {}).get("agent1", []))
        + len(build_dashboard_payload().get("tradeHistory", {}).get("agent2", []))
        + len(build_dashboard_payload().get("tradeHistory", {}).get("agent3", []))
        + len(build_dashboard_payload().get("tradeHistory", {}).get("agent4", [])),
    }

    report["ok"] = True
    return report
