"""WeeklyReviewAgent — 규칙 사전분류 + DeepSeek 최종 판단."""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.kr_intraday_slack.llm_client import call_primary_json, is_primary_configured

logger = logging.getLogger("weekly_watchlist.review")

ACTION_KEEP = "keep"
ACTION_WEAKEN = "weaken"
ACTION_REMOVE = "remove_candidate"
ACTION_DATA_CHECK = "data_check_needed"

REASON_CAUTION = "caution_watch"
REASON_REMOVE_MULTI = "remove_multi_weak"
REASON_MOMENTUM_WEAKEN = "momentum_weaken"
REASON_SLACK_FATIGUE = "slack_alert_fatigue"
REASON_KEEP_STRONG = "keep_strong"
REASON_KEEP_NEUTRAL = "keep_neutral"

REMOVE_MIN_SIGNALS = 4
REMOVE_MIN_MOMENTUM_SIGNALS = 2
REMOVE_EXCEPTION_MOMENTUM_SIGNALS = 3
REMOVE_EXCEPTION_MAX_RS = 30
REMOVE_EXCEPTION_MAX_PRIORITY = 25
STRONG_REMOVE_MIN_SIGNALS = 5
REMOVE_LEVEL_STRONG = "strong_remove"
REMOVE_LEVEL_REVIEW = "review_remove"
SEVERITY_LABEL_STRONG = "강한 제외"
SEVERITY_LABEL_REVIEW = "제외 검토"
MOMENTUM_REMOVE_FLAGS = frozenset({"weak_return_5d", "low_rs", "tv_decline"})
KEEP_MIN_GOOD_SIGNALS = 2

ALL_ACTIONS = frozenset(
    {ACTION_KEEP, ACTION_WEAKEN, ACTION_REMOVE, ACTION_DATA_CHECK}
)


def _needs_data_check(row: dict[str, Any]) -> bool:
    """5거래일 미만만 데이터 확인 필요 — partial/ok_5d/ok_10d는 평가 포함."""
    return str(row.get("data_status") or row.get("data_quality") or "") == "missing_ohlcv"


def _data_check_reason(row: dict[str, Any]) -> str:
    fetch = row.get("ohlcv_fetch") or {}
    rows = row.get("ohlcv_rows") or fetch.get("row_count") or 0
    if rows:
        return f"최근 OHLCV {rows}일만 수집됨 (5일 미만)"
    return "최근 OHLCV 수집 실패"


def _data_check_one_line(row: dict[str, Any]) -> str:
    return _data_check_reason(row)


def _apply_data_guard(stock: dict[str, Any]) -> dict[str, Any]:
    """메트릭 부족 시 약세·제외 단정 방지."""
    metrics = stock.get("metrics") or {}
    if not _needs_data_check(metrics):
        return stock
    return {
        **stock,
        "action": ACTION_DATA_CHECK,
        "reasons": [_data_check_reason(metrics)],
        "one_line": _data_check_one_line(metrics),
        "priority_score": min(int(stock.get("priority_score") or 50), 15),
    }


def _metric_row(row: dict[str, Any], sector_mood: dict[str, str]) -> dict[str, Any]:
    sector = str(row.get("sector", ""))
    mood = sector_mood.get(sector, "neutral")
    return {
        "sector": sector,
        "mood": mood,
        "ret5": float(row.get("return_5d") or 0),
        "tv_g": float(row.get("tv_growth_5d_vs_10d") or 0),
        "dd": float(row.get("drawdown_from_recent_high") or 0),
        "pos52": float(row.get("position_vs_52w_high") or 0),
        "rs": float(row.get("sector_relative_strength") or 50),
        "sent": int(row.get("recent_slack_sent_count") or 0),
        "cand": int(row.get("recent_candidate_count") or 0),
    }


def count_remove_signals(row: dict[str, Any], sector_mood: dict[str, str]) -> tuple[int, list[str]]:
    """제외 후보용 약세 신호 — REMOVE_MIN_SIGNALS개 이상일 때만 remove."""
    m = _metric_row(row, sector_mood)
    flags: list[str] = []
    if m["ret5"] < -3:
        flags.append("weak_return_5d")
    if m["rs"] < 35:
        flags.append("low_rs")
    if m["tv_g"] < -0.08:
        flags.append("tv_decline")
    if m["dd"] >= 12:
        flags.append("large_drawdown")
    if 0 < m["pos52"] < 0.85:
        flags.append("below_52w_high")
    if m["mood"] == "weak":
        flags.append("weak_sector_mood")
    return len(flags), flags


def momentum_weak_count(remove_flags: list[str]) -> int:
    return sum(1 for f in remove_flags if f in MOMENTUM_REMOVE_FLAGS)


def is_remove_eligible(
    remove_flags: list[str],
    *,
    row: dict[str, Any] | None = None,
    priority_score: int | None = None,
) -> bool:
    """기본: 신호 4개+ & 모멘텀 2개+. 예외: 모멘텀 3개+ & (RS<30 | priority≤25)."""
    total_n = len(remove_flags)
    momentum_n = momentum_weak_count(remove_flags)

    if momentum_n >= REMOVE_EXCEPTION_MOMENTUM_SIGNALS:
        if row is not None and float(row.get("sector_relative_strength") or 50) < REMOVE_EXCEPTION_MAX_RS:
            return True
        if (
            priority_score is not None
            and priority_score <= REMOVE_EXCEPTION_MAX_PRIORITY
        ):
            return True

    if (
        total_n >= REMOVE_MIN_SIGNALS
        and momentum_n >= REMOVE_MIN_MOMENTUM_SIGNALS
    ):
        return True

    return False


def classify_remove_level(
    *,
    remove_signal_count: int,
    momentum_weak_count: int,
    priority_score: int,
) -> tuple[str, str]:
    """remove_candidate 내부 강도 — action enum은 동일."""
    if (
        remove_signal_count >= STRONG_REMOVE_MIN_SIGNALS
        or momentum_weak_count >= REMOVE_EXCEPTION_MOMENTUM_SIGNALS
        or priority_score <= REMOVE_EXCEPTION_MAX_PRIORITY
    ):
        return REMOVE_LEVEL_STRONG, SEVERITY_LABEL_STRONG
    return REMOVE_LEVEL_REVIEW, SEVERITY_LABEL_REVIEW


def count_keep_signals(row: dict[str, Any]) -> int:
    """수익·RS·거래대금 중 2개 이상 양호면 keep 우선."""
    m = _metric_row(row, {"": "neutral"})
    good = 0
    if m["ret5"] >= 0.5:
        good += 1
    if m["rs"] >= 55:
        good += 1
    if m["tv_g"] >= 0:
        good += 1
    return good


def _is_explicit_keep(row: dict[str, Any], sector_mood: dict[str, str]) -> bool:
    m = _metric_row(row, sector_mood)
    if m["mood"] == "strong" and m["ret5"] >= 1 and m["rs"] >= 60:
        return True
    if m["ret5"] >= 3 and m["tv_g"] >= 0.1:
        return True
    return False


def _is_caution_profile(
    row: dict[str, Any],
    sector_mood: dict[str, str],
    remove_n: int,
    remove_flags: list[str] | None = None,
) -> bool:
    """remove 직전 중간 그룹 — action은 weaken, reason_code로 구분."""
    if remove_flags is not None and is_remove_eligible(remove_flags, row=row):
        return False
    m = _metric_row(row, sector_mood)
    if m["ret5"] < -2 and m["rs"] < 40:
        return True
    if m["dd"] >= 8 and m["tv_g"] < 0:
        return True
    if remove_n >= 2:
        return True
    if remove_n == 1 and (m["dd"] >= 10 or m["pos52"] < 0.88):
        return True
    return False


def _severity_score(
    action: str,
    priority: int,
    remove_n: int,
    *,
    remove_level: str | None = None,
) -> int:
    if action == ACTION_DATA_CHECK:
        return 5
    if action == ACTION_REMOVE:
        base = max(5, 35 - remove_n * 8)
        if remove_level == REMOVE_LEVEL_STRONG:
            return min(base, 18)
        return base
    return max(10, min(100, priority))


def _apply_remove_level_fields(stock: dict[str, Any]) -> dict[str, Any]:
    """remove_level·severity_label·momentum_weak_count 보강."""
    flags = list(stock.get("remove_flags") or [])
    remove_n = int(stock.get("remove_signal_count") if stock.get("remove_signal_count") is not None else len(flags))
    mom_n = stock.get("momentum_weak_count")
    if mom_n is None:
        mom_n = momentum_weak_count(flags)
    pri = int(stock.get("priority_score") or 50)

    out = {
        **stock,
        "remove_signal_count": remove_n,
        "remove_flags": flags,
        "momentum_weak_count": mom_n,
    }

    if str(stock.get("action")) != ACTION_REMOVE:
        return {**out, "remove_level": None, "severity_label": None}

    level, label = classify_remove_level(
        remove_signal_count=remove_n,
        momentum_weak_count=int(mom_n),
        priority_score=pri,
    )
    out["remove_level"] = level
    out["severity_label"] = label
    out["severity_score"] = _severity_score(
        ACTION_REMOVE, pri, remove_n, remove_level=level
    )
    return out


def _enrich_rule_fields(
    *,
    action: str,
    reasons: list[str],
    priority: int,
    reason_code: str | None,
    remove_n: int,
    remove_flags: list[str],
) -> dict[str, Any]:
    mom_n = momentum_weak_count(remove_flags)
    level: str | None = None
    label: str | None = None
    if action == ACTION_REMOVE:
        level, label = classify_remove_level(
            remove_signal_count=remove_n,
            momentum_weak_count=mom_n,
            priority_score=priority,
        )
    return {
        "rule_action": action,
        "rule_reasons": reasons,
        "rule_priority": priority,
        "reason_code": reason_code,
        "remove_signal_count": remove_n,
        "remove_flags": remove_flags,
        "momentum_weak_count": mom_n,
        "remove_level": level,
        "severity_label": label,
        "severity_score": _severity_score(
            action, priority, remove_n, remove_level=level
        ),
    }


def rule_precheck(row: dict[str, Any], sector_mood: dict[str, str]) -> dict[str, Any]:
    """LLM 입력용 규칙 힌트. 데이터 부족이면 모멘텀 판단 없음."""
    m = _metric_row(row, sector_mood)

    if _needs_data_check(row):
        return _enrich_rule_fields(
            action=ACTION_DATA_CHECK,
            reasons=[_data_check_reason(row)],
            priority=10,
            reason_code=None,
            remove_n=0,
            remove_flags=[],
        ) | {"sector_mood": m["mood"]}

    remove_n, remove_flags = count_remove_signals(row, sector_mood)
    keep_n = count_keep_signals(row)
    reasons: list[str] = []
    reason_code: str | None = None

    if is_remove_eligible(remove_flags, row=row):
        action = ACTION_REMOVE
        reason_code = REASON_REMOVE_MULTI
        reasons.append(
            f"복합 약세 신호 {remove_n}개 ({', '.join(remove_flags[:4])})"
        )
        mom_n = momentum_weak_count(remove_flags)
        level_probe, _ = classify_remove_level(
            remove_signal_count=remove_n,
            momentum_weak_count=mom_n,
            priority_score=50,
        )
        if level_probe == REMOVE_LEVEL_STRONG:
            priority = min(REMOVE_EXCEPTION_MAX_PRIORITY, max(18, 32 - remove_n * 2))
        else:
            priority = 28
    elif keep_n >= KEEP_MIN_GOOD_SIGNALS or _is_explicit_keep(row, sector_mood):
        action = ACTION_KEEP
        reason_code = REASON_KEEP_STRONG if _is_explicit_keep(row, sector_mood) else REASON_KEEP_NEUTRAL
        if keep_n >= KEEP_MIN_GOOD_SIGNALS:
            reasons.append("5일 수익·RS·거래대금 중 2개 이상 양호")
        elif m["mood"] == "strong":
            reasons.append("섹터 강세·상대 강도 양호")
        else:
            reasons.append("주간 수익·거래대금 개선")
        priority = 85 if reason_code == REASON_KEEP_STRONG else 58
    elif _is_caution_profile(row, sector_mood, remove_n, remove_flags) or (
        remove_n >= 2 and not is_remove_eligible(remove_flags, row=row)
    ):
        action = ACTION_WEAKEN
        reason_code = REASON_CAUTION
        if m["dd"] >= 8 and m["tv_g"] < 0:
            reasons.append("고점 대비 조정·거래대금 둔화 — 제외 전 주의")
        elif m["ret5"] < -2 and m["rs"] < 40:
            reasons.append("수익·섹터 RS 동반 약화 — 반등 전 관심 축소")
        else:
            reasons.append(f"약세 신호 {remove_n}개 — 제외 검토 전 단계")
        priority = 36
    elif m["mood"] == "weak" or (m["ret5"] < -2 and m["tv_g"] < -0.05):
        action = ACTION_WEAKEN
        reason_code = REASON_MOMENTUM_WEAKEN
        reasons.append("섹터·주간 모멘텀 둔화 (거래대금·RS 완전 붕괴 전)")
        priority = 44
    elif m["sent"] >= 3 and m["ret5"] < 0 and m["cand"] >= 5:
        action = ACTION_WEAKEN
        reason_code = REASON_SLACK_FATIGUE
        reasons.append("알림 빈도 대비 주간 성과 부진")
        priority = 42
    else:
        action = ACTION_KEEP
        reason_code = REASON_KEEP_NEUTRAL
        reasons.append("중립 구간 — 추가 확인")
        priority = 55

    fields = _enrich_rule_fields(
        action=action,
        reasons=reasons,
        priority=priority,
        reason_code=reason_code,
        remove_n=remove_n,
        remove_flags=remove_flags,
    )
    if action == ACTION_REMOVE:
        mom_n = fields["momentum_weak_count"]
        level, label = classify_remove_level(
            remove_signal_count=remove_n,
            momentum_weak_count=mom_n,
            priority_score=priority,
        )
        fields["remove_level"] = level
        fields["severity_label"] = label
        fields["severity_score"] = _severity_score(
            action, priority, remove_n, remove_level=level
        )
    return fields | {"sector_mood": m["mood"]}


def refine_stock_action(stock: dict[str, Any], sector_mood: dict[str, str]) -> dict[str, Any]:
    """LLM/규칙 결과에 remove 임계·caution 메타 보정."""
    metrics = stock.get("metrics") or stock
    if _needs_data_check(metrics):
        return _apply_data_guard(stock)

    remove_n, remove_flags = count_remove_signals(metrics, sector_mood)
    action = str(stock.get("action", ACTION_KEEP))
    reason_code = stock.get("reason_code")

    pri = int(stock.get("priority_score") or 50)
    if action == ACTION_REMOVE and not is_remove_eligible(
        remove_flags, row=metrics, priority_score=pri
    ):
        if _is_caution_profile(metrics, sector_mood, remove_n, remove_flags):
            action = ACTION_WEAKEN
            reason_code = REASON_CAUTION
            reasons = stock.get("reasons") or []
            if not reasons:
                reasons = [f"제외 신호 {remove_n}개 — 주의 관찰로 조정"]
            stock = {
                **stock,
                "action": action,
                "reason_code": reason_code,
                "reasons": reasons[:3],
                "priority_score": min(int(stock.get("priority_score") or 50), 38),
            }
        else:
            stock = {
                **stock,
                "action": ACTION_WEAKEN,
                "reason_code": REASON_MOMENTUM_WEAKEN,
                "priority_score": min(int(stock.get("priority_score") or 50), 44),
            }

    elif action == ACTION_WEAKEN and not reason_code:
        if _is_caution_profile(metrics, sector_mood, remove_n, remove_flags):
            reason_code = REASON_CAUTION
        else:
            reason_code = REASON_MOMENTUM_WEAKEN
        stock = {**stock, "reason_code": reason_code}

    return _apply_remove_level_fields(
        {
            **stock,
            "remove_signal_count": remove_n,
            "remove_flags": remove_flags,
        }
    )


def build_review_prompt(
    metrics: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    as_of_date: str,
) -> str:
    enriched = []
    for row in metrics:
        hint = rule_precheck(row, sector_mood)
        enriched.append({**row, **hint})

    return f"""주간 관심종목 25개 재평가 (MVP 1단계).
기준일: {as_of_date}
신규 발굴·kr_watchlist.json 자동 수정 금지. 기존 25종목만 평가.

섹터 분위기: {json.dumps(sector_mood, ensure_ascii=False)}

종목 메트릭(JSON):
{json.dumps(enriched, ensure_ascii=False, indent=0)}

각 종목에 대해 action을 하나만 선택:
- keep: 핵심 유지
- weaken: 관찰 약화 (우선순위 낮춤)
- remove_candidate: 제외 후보 (다음 주 정리 검토, 데이터가 충분할 때만)
- data_check_needed: 데이터 확인 필요 (OHLCV 부족·수집 실패, 약세 단정 금지)

JSON만 반환:
{{
  "summary": "주간 한 줄 요약",
  "sector_notes": {{"섹터명": "한 줄"}},
  "stocks": [
    {{
      "ticker": "000000",
      "symbol": "종목명",
      "sector": "섹터",
      "action": "keep|weaken|remove_candidate|data_check_needed",
      "priority_score": 0-100,
      "reasons": ["완성된 한국어 문장"],
      "risks": ["완성된 한국어 문장"],
      "one_line": "슬랙용 한 줄"
    }}
  ],
  "top_keep": ["티커 최대 5개"],
  "remove_candidates": ["티커"],
  "weaken_list": ["티커"],
  "data_check_needed": ["티커"]
}}
"""


def _normalize_judgment(
    parsed: dict[str, Any],
    metrics: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    llm_used: bool = False,
) -> dict[str, Any]:
    """LLM 응답 정규화 + 누락 종목 규칙 보완."""
    by_ticker = {str(r.get("ticker", "")).zfill(6): r for r in metrics}
    stocks_in = parsed.get("stocks") if isinstance(parsed.get("stocks"), list) else []
    merged_stocks: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in stocks_in:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker", "")).zfill(6)
        if not ticker or ticker not in by_ticker:
            continue
        seen.add(ticker)
        base = by_ticker[ticker]
        action = str(item.get("action", ACTION_KEEP)).strip()
        if action not in ALL_ACTIONS:
            action = ACTION_KEEP
        stock = {
            "ticker": ticker,
            "symbol": item.get("symbol") or base.get("symbol"),
            "sector": item.get("sector") or base.get("sector"),
            "action": action,
            "priority_score": int(item.get("priority_score") or 50),
            "reasons": list(item.get("reasons") or [])[:3],
            "risks": list(item.get("risks") or [])[:2],
            "one_line": str(item.get("one_line") or "").strip(),
            "reason_code": item.get("reason_code"),
            "metrics": base,
        }
        merged_stocks.append(
            _apply_data_guard(refine_stock_action(stock, sector_mood))
        )

    for ticker, base in by_ticker.items():
        if ticker in seen:
            continue
        hint = rule_precheck(base, sector_mood)
        merged_stocks.append(
            _apply_data_guard(
                refine_stock_action(
                    {
                        "ticker": ticker,
                        "symbol": base.get("symbol"),
                        "sector": base.get("sector"),
                        "action": hint["rule_action"],
                        "priority_score": hint["rule_priority"],
                        "reasons": hint["rule_reasons"],
                        "reason_code": hint.get("reason_code"),
                        "risks": [],
                        "one_line": hint["rule_reasons"][0] if hint["rule_reasons"] else "",
                        "metrics": base,
                        "fallback_rule": True,
                    },
                    sector_mood,
                )
            )
        )

    keep = [s for s in merged_stocks if s["action"] == ACTION_KEEP]
    weaken = [s for s in merged_stocks if s["action"] == ACTION_WEAKEN]
    caution = [
        s for s in weaken if s.get("reason_code") == REASON_CAUTION
    ]
    weaken_mild = [s for s in weaken if s.get("reason_code") != REASON_CAUTION]
    remove = [s for s in merged_stocks if s["action"] == ACTION_REMOVE]
    strong_remove = [
        s for s in remove if s.get("remove_level") == REMOVE_LEVEL_STRONG
    ]
    review_remove = [
        s for s in remove if s.get("remove_level") != REMOVE_LEVEL_STRONG
    ]
    data_check = [s for s in merged_stocks if s["action"] == ACTION_DATA_CHECK]

    keep.sort(key=lambda s: (-int(s.get("priority_score") or 0), str(s.get("ticker"))))
    top_keep = [s["ticker"] for s in keep[:5]]
    if parsed.get("top_keep"):
        top_keep = [str(t).zfill(6) for t in parsed["top_keep"]][:5]

    return {
        "summary": str(parsed.get("summary") or "주간 관심종목 재평가 완료").strip(),
        "sector_notes": parsed.get("sector_notes")
        if isinstance(parsed.get("sector_notes"), dict)
        else {},
        "sector_mood": sector_mood,
        "stocks": merged_stocks,
        "top_keep": top_keep,
        "remove_candidates": [s["ticker"] for s in remove],
        "strong_remove_list": [s["ticker"] for s in strong_remove],
        "review_remove_list": [s["ticker"] for s in review_remove],
        "weaken_list": [s["ticker"] for s in weaken],
        "caution_list": [s["ticker"] for s in caution],
        "data_check_needed": [s["ticker"] for s in data_check],
        "keep_count": len(keep),
        "weaken_count": len(weaken_mild),
        "caution_count": len(caution),
        "remove_count": len(remove),
        "strong_remove_count": len(strong_remove),
        "review_remove_count": len(review_remove),
        "data_check_count": len(data_check),
        "llm_used": llm_used,
    }


def rule_only_judgment(
    metrics: list[dict[str, Any]],
    sector_mood: dict[str, str],
) -> dict[str, Any]:
    """규칙만 판단 (LLM API 호출 없음)."""
    stocks: list[dict[str, Any]] = []
    for row in metrics:
        hint = rule_precheck(row, sector_mood)
        stocks.append(
            _apply_data_guard(
                refine_stock_action(
                    {
                        "ticker": row["ticker"],
                        "symbol": row.get("symbol"),
                        "sector": row.get("sector"),
                        "action": hint["rule_action"],
                        "priority_score": hint["rule_priority"],
                        "reasons": hint["rule_reasons"],
                        "reason_code": hint.get("reason_code"),
                        "risks": [],
                        "one_line": hint["rule_reasons"][0] if hint["rule_reasons"] else "",
                        "metrics": row,
                    },
                    sector_mood,
                )
            )
        )
    out = _normalize_judgment(
        {
            "summary": "규칙 기반 주간 재평가 (LLM 미사용)",
            "stocks": stocks,
        },
        metrics,
        sector_mood,
        llm_used=False,
    )
    out["llm_used"] = False
    return out


def run_weekly_review(
    metrics: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    as_of_date: str,
    use_llm: bool = True,
) -> tuple[dict[str, Any], str | None]:
    if not use_llm:
        logger.info("[weekly] LLM skipped (--no-llm / use_llm=False)")
        return rule_only_judgment(metrics, sector_mood), None

    if not is_primary_configured():
        logger.info("[weekly] DeepSeek 미설정 — 규칙만 사용")
        return rule_only_judgment(metrics, sector_mood), None

    prompt = build_review_prompt(metrics, sector_mood, as_of_date=as_of_date)
    parsed, err = call_primary_json(prompt, agent="weekly_watchlist_review")
    if parsed:
        logger.info("[weekly] DeepSeek 호출 완료")
        return _normalize_judgment(parsed, metrics, sector_mood, llm_used=True), None

    logger.warning("DeepSeek 실패, 규칙 폴백: %s", err)
    judgment = rule_only_judgment(metrics, sector_mood)
    judgment["llm_error"] = err
    return judgment, err
