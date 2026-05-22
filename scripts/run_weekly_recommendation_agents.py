# -*- coding: utf-8 -*-
"""주간 모의투자 종목 선정 에이전트 팀 실행."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.ai import model_config
from agents.mock_trading.candidate_context import enrich_candidates
from agents.mock_trading.grok_validator import run_grok_validation
from agents.mock_trading.models import AGENT_SPECS, GROK_VALIDATOR_KEY
from agents.mock_trading.recommendation_agents import (
    check_provider_ready,
    resolve_model_id,
    run_all_recommendation_agents,
)
from agents.mock_trading.recommendation_merge import merge_recommendations
from agents.mock_trading.compact_input import (
    load_compact_universe,
    load_universe_map_from_ai_input,
)
from agents.mock_trading.universe_builder import build_universe
from data.api_env import ensure_env_loaded

DATA_DIR = ROOT / "data" / "mock_trading"
UNIVERSE_PATH = DATA_DIR / "candidate_universe.json"
COMPACT_PATH = DATA_DIR / "ai_candidate_context_compact.json"
AI_INPUT_PATH = DATA_DIR / "ai_input_candidates.json"
WEEKLY_PATH = DATA_DIR / "weekly_recommendations.json"
MERGED_PATH = DATA_DIR / "merged_recommendations.json"
KST = ZoneInfo("Asia/Seoul")


def _week_id(now: datetime | None = None) -> str:
    dt = now or datetime.now(KST)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _agent_stubs(*, mode: str, error: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in AGENT_SPECS:
        ready, err = check_provider_ready(spec.provider)
        rows.append(
            {
                "agent_key": spec.agent_key,
                "display_name": spec.display_name,
                "perspective": spec.perspective,
                "provider": spec.provider,
                "model_id": resolve_model_id(spec),
                "recommendations": [],
                "skipped": True,
                "skip_reason": error or (None if ready else err),
                "provider_ready": ready,
            }
        )
    return rows


def _provider_audit() -> dict[str, Any]:
    audit: dict[str, Any] = {"agents": [], "grok": {}}
    for spec in AGENT_SPECS:
        ready, err = check_provider_ready(spec.provider)
        audit["agents"].append(
            {
                "agent_key": spec.agent_key,
                "provider": spec.provider,
                "model_id": resolve_model_id(spec),
                "ready": ready,
                "error": err or None,
            }
        )
    grok_ready, grok_err = check_provider_ready("grok")
    audit["grok"] = {
        "agent_key": GROK_VALIDATOR_KEY,
        "model_id": model_config.GROK_MODEL_ID,
        "ready": grok_ready,
        "error": grok_err or None,
    }
    return audit


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="주간 모의투자 종목 선정 에이전트")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="AI 호출 없이 후보군·JSON 구조만 생성",
    )
    parser.add_argument(
        "--live-ai",
        action="store_true",
        help="4개 추천 에이전트 + Grok 검증 실제 호출",
    )
    parser.add_argument(
        "--use-kis-prices",
        action="store_true",
        help="후보군 가격을 KIS로 조회 (target_sector 모드에서 필수)",
    )
    parser.add_argument(
        "--kis-price-limit",
        type=int,
        default=0,
        help="KIS 가격 조회 최대 종목 수 (0=무제한, keyword_discovery 전용)",
    )
    parser.add_argument(
        "--universe-mode",
        choices=("target_sector", "keyword_discovery"),
        default="target_sector",
        help="후보 유니버스 소스 (기본: target_sector_universe included)",
    )
    parser.add_argument(
        "--max-enrich",
        type=int,
        default=0,
        help="metrics/뉴스 보강 최대 종목 수 (0=전체, dry-run은 뉴스 생략)",
    )
    args = parser.parse_args()

    if args.live_ai and args.dry_run:
        print("오류: --live-ai 와 --dry-run 은 동시에 사용할 수 없습니다.")
        return 1

    dry_run = args.dry_run or not args.live_ai
    ensure_env_loaded()
    now = datetime.now(KST)
    week_id = _week_id(now)

    use_kis = args.use_kis_prices
    if args.universe_mode == "target_sector" and not use_kis:
        print("target_sector 모드: KIS 현재가 필수 — --use-kis-prices 자동 적용")
        use_kis = True

    input_source = ""
    enrich_notes: list[str] = []

    if args.live_ai:
        print("live-ai: ai_candidate_context_compact.json 입력 (후보군 재생성 없음)")
        candidates, compact_meta, compact_err = load_compact_universe(COMPACT_PATH)
        if compact_err or not candidates:
            print(f"실패: {compact_err or 'compact 후보 0건'}")
            return 1
        summary = {
            "ai_input_source": COMPACT_PATH.name,
            "ai_input_candidate_count": len(candidates),
            "selection_rule": compact_meta.get("selection_rule"),
            "compact_generated_at": compact_meta.get("generated_at"),
        }
        errors: list[str] = []
        input_source = COMPACT_PATH.name
        built = {"kosdaq_available": True}
    else:
        print(
            f"week_id={week_id} mode=dry-run universe={args.universe_mode} "
            f"kis_prices={use_kis}"
        )
        built = build_universe(
            universe_mode=args.universe_mode,
            use_kis_prices=use_kis,
            kis_price_limit=args.kis_price_limit,
            collect_metrics=True,
        )
        if not built.get("kosdaq_available"):
            print("실패: 유니버스 로드 불가")
            for e in built.get("errors") or []:
                print(f" - {e}")
            return 1
        candidates = list(built.get("candidates") or [])
        summary = built.get("universe_summary") or {}
        errors = list(built.get("errors") or [])
        if args.universe_mode == "keyword_discovery" and candidates:
            max_enrich = args.max_enrich if args.max_enrich > 0 else (30 if dry_run else 0)
            candidates, enrich_notes = enrich_candidates(
                candidates,
                max_enrich=max_enrich,
                skip_news=dry_run,
            )
        elif dry_run:
            enrich_notes.append(
                "target_sector: 메트릭은 universe_builder에서 일괄 수집, 뉴스/공시 생략"
            )
        universe_doc = {
            "week_id": week_id,
            "generated_at": now.isoformat(timespec="seconds"),
            "mode": "dry-run",
            "source_universe": (
                "target_sector_universe.included_only"
                if args.universe_mode == "target_sector"
                else "keyword_discovery"
            ),
            "universe_summary": summary,
            "candidates": candidates,
            "excluded_by_market": built.get("excluded_by_market") or [],
            "excluded_by_price": built.get("excluded_by_price") or [],
            "excluded_by_risk": built.get("excluded_by_risk") or [],
            "excluded_by_liquidity": built.get("excluded_by_liquidity") or [],
            "lookup_failures": built.get("lookup_failures") or [],
            "errors": errors,
            "notes": notes + enrich_notes,
        }
        _write_json(UNIVERSE_PATH, universe_doc)
        input_source = UNIVERSE_PATH.name

    if args.live_ai:
        print(
            f"week_id={week_id} mode=live-ai input={input_source} "
            f"candidates={len(candidates)}"
        )

    agent_results: list[dict[str, Any]] = []
    grok_rows: list[dict[str, Any]] = []
    pipeline_errors: list[str] = []

    if dry_run:
        agent_results = _agent_stubs(mode="dry-run", error="--dry-run: AI 호출 생략")
        grok_rows = []
    else:
        provider_audit = _provider_audit()
        not_ready = [
            a["agent_key"]
            for a in provider_audit["agents"]
            if not a["ready"]
        ]
        if not_ready:
            pipeline_errors.append(f"AI provider 미준비: {', '.join(not_ready)}")
            print("실패: 추천 AI provider 미준비")
            for e in pipeline_errors:
                print(f" - {e}")
            agent_results = _agent_stubs(mode="live-ai-blocked", error="provider 미준비")
            grok_rows = []
        else:
            print(f"추천 AI 실행 중 ({len(candidates)}종 입력)...")
            agent_results, agent_errors = run_all_recommendation_agents(candidates)
            pipeline_errors.extend(agent_errors)
            if provider_audit["grok"]["ready"]:
                print("Grok 검증 실행 중...")
                grok_rows, grok_err = run_grok_validation(agent_results)
                if grok_err:
                    pipeline_errors.append(f"grok: {grok_err}")
            else:
                grok_rows = [
                    {
                        "status": "skipped",
                        "skip_reason": provider_audit["grok"].get("error")
                        or "GROK 미준비",
                    }
                ]
                pipeline_errors.append(
                    f"Grok skipped: {provider_audit['grok'].get('error')}"
                )

    weekly_doc = {
        "week_id": week_id,
        "generated_at": now.isoformat(timespec="seconds"),
        "mode": "dry-run" if dry_run else "live-ai",
        "input_source": input_source,
        "universe_summary": summary,
        "agents": agent_results,
        "grok_validation": grok_rows,
        "pipeline_errors": pipeline_errors,
        "provider_audit": _provider_audit() if not dry_run else None,
        "ai_executed": not dry_run,
    }
    _write_json(WEEKLY_PATH, weekly_doc)

    universe_map = load_universe_map_from_ai_input(AI_INPUT_PATH)
    if not universe_map:
        universe_map = {str(c["ticker"]).zfill(6): c for c in candidates}
    merged_body = merge_recommendations(agent_results, grok_rows, universe_map)
    merged_doc = {
        "week_id": week_id,
        "generated_at": now.isoformat(timespec="seconds"),
        "mode": "dry-run" if dry_run else "live-ai",
        **merged_body,
    }
    _write_json(MERGED_PATH, merged_doc)

    if not dry_run:
        try:
            from agents.mock_trading.plain_language_editor import run_plain_language_editor

            merged_doc = run_plain_language_editor(merged_doc, weekly_doc)
            _write_json(MERGED_PATH, merged_doc)
            pl_meta = merged_doc.get("plain_language_editor") or {}
            print(
                f" AI 쉬운 해설: model={pl_meta.get('model_id')} "
                f"gemini={pl_meta.get('gemini_cards', 0)} "
                f"fallback={pl_meta.get('fallback_cards', 0)}"
            )
        except Exception as exc:
            print(f" AI 쉬운 해설 경고: {type(exc).__name__}: {exc}")

        try:
            from agents.mock_trading.weekly_recommendations_store import (
                save_weekly_recommendations,
            )

            fb_save = save_weekly_recommendations(week_id, merged_doc, weekly_doc)
            print(
                f" Firebase {fb_save.get('firestore_path')}: "
                f"{'OK' if fb_save.get('ok') else 'FAIL'}"
                f" ({fb_save.get('persist_backend')})"
            )
            if not fb_save.get("ok") and fb_save.get("error"):
                print(f"  Firebase 저장 경고: {fb_save.get('error')}")
        except Exception as exc:
            print(f" Firebase 저장 경고: {type(exc).__name__}: {exc}")

    print("")
    print("=== 후보군 (target_sector + KIS) ===")
    if args.universe_mode == "target_sector":
        print(f" included 풀: {summary.get('included_total', 0)}")
        print(f" KOSDAQ verified: {summary.get('market_verified_kosdaq', 0)}")
        print(f" 시장 제외(KOSPI 등): {summary.get('market_excluded', 0)}")
        print(f" 시장 미확인 제외: {summary.get('market_unverified', 0)}")
        print(f" KIS 가격 조회: {summary.get('price_checked', 0)}")
        print(f" 조회 실패: {summary.get('price_lookup_failed', 0)}")
        print(f" 위험 제외: {summary.get('risk_excluded', 0)}")
        print(f" 가격 초과 제외: {summary.get('price_excluded', 0)}")
        print(f" 59,000원 이하: {summary.get('price_under_59000', 0)}")
        print(f" 유동성 제외(<5억): {summary.get('liquidity_excluded', 0)}")
        by_sec = summary.get("final_by_sector") or {}
        for k, v in by_sec.items():
            print(f"   - {k}: {v}")
    else:
        print(f" 코스닥 조회: {summary.get('kosdaq_total_checked', 0)}")
        print(f" 키워드 매칭: {summary.get('industry_matched', 0)}")
        print(f" 59,000원 이하: {summary.get('price_under_59000', 0)}")
    print(f" 최종 후보: {summary.get('final_candidate_count', 0)}")
    print(f" 저장: {UNIVERSE_PATH}")

    if errors:
        print(" 경고:")
        for e in errors[:5]:
            print(f"  - {e}")

    if dry_run:
        print("")
        print("=== dry-run ===")
        print(f" weekly_recommendations: AI 스킵 ({WEEKLY_PATH})")
        print(f" merged_cards: {merged_body.get('ticker_count', 0)}건")
    else:
        print("")
        print("=== live-ai 완료 ===")
        print(f" weekly: {WEEKLY_PATH}")
        print(f" merged: {MERGED_PATH} ({merged_body.get('ticker_count', 0)}종)")
        for ar in agent_results:
            n = len(ar.get("recommendations") or [])
            err = ar.get("error")
            print(f" - {ar.get('agent_key')}: model={ar.get('model_id')} picks={n}" + (
                f" err={err}" if err else ""
            ))

    return 0 if candidates or dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
