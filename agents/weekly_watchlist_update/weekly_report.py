"""주간 MD·JSON 제안서·Slack 요약."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agents.weekly_watchlist_update.news_context import (
    build_next_week_checkpoints,
    clean_display_text,
    format_slack_issue_line,
    normalize_dart_issue_title,
)
from agents.weekly_watchlist_update.weekly_review import (
    REASON_CAUTION,
    REMOVE_LEVEL_REVIEW,
    REMOVE_LEVEL_STRONG,
    SEVERITY_LABEL_REVIEW,
    SEVERITY_LABEL_STRONG,
)

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "reports" / "weekly_watchlist"
PROPOSAL_DIR = ROOT / "data" / "proposals" / "watchlist_review"

MOOD_KO = {"strong": "강세", "neutral": "중립", "weak": "약세"}
ACTION_SECTIONS: tuple[tuple[str, str], ...] = (
    ("data_check_needed", "데이터 확인 필요"),
    ("remove_candidate", "제외 후보"),
    ("weaken", "관찰 약화"),
    ("keep", "유지"),
)

SLACK_SECTION_MAX = 8
SLACK_STRONG_REMOVE_MAX = 6
SLACK_REVIEW_REMOVE_MAX = 2
SLACK_REVIEW_REMOVE_MIN = 1

# Slack 전용 — proposal/MD는 ACTION_SECTIONS 그대로
SLACK_TRADING_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("keep", "🟢 핵심 유지", "눌림/돌파 시 우선 확인"),
    ("weaken", "🟡 관찰 약화", "추격 금지, 거래대금 회복 확인"),
    ("caution", "⚠️ 주의 관찰", "반등 전까지 관심도 낮춤"),
    ("remove_candidate", "🚫 제외 후보", "단기 관심종목에서 제외 검토"),
    ("data_check_needed", "🧪 데이터 확인 필요", "OHLCV 또는 수급 데이터 확인 필요"),
)


def _kst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def build_proposal_payload(
    *,
    as_of_date: str,
    metrics: list[dict[str, Any]],
    judgment: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "weekly_watchlist_mvp_v1",
        "as_of_date": as_of_date,
        "generated_at": _kst_now().isoformat(),
        "scope": "existing_25_only",
        "auto_apply_watchlist": False,
        "metrics": metrics,
        "judgment": judgment,
    }


def _format_rcept_dt(raw: str) -> str:
    s = str(raw or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _append_stock_news_block(lines: list[str], stock: dict[str, Any]) -> None:
    ctx = stock.get("news_context") or {}
    tags = ctx.get("issue_tags") or []
    if tags:
        lines.append(f"- 이슈 태그: {', '.join(tags)}")
    llm_sum = ctx.get("issue_summary")
    if llm_sum:
        lines.append(f"- LLM 요약: {llm_sum}")
    items: list[str] = []
    for d in (ctx.get("dart_disclosures") or [])[:3]:
        nm = str(
            d.get("report_nm_normalized")
            or normalize_dart_issue_title(str(d.get("report_nm") or ""))
        )
        dt = _format_rcept_dt(str(d.get("rcept_dt") or ""))
        items.append(f"[DART] {nm}" + (f" — {dt}" if dt else ""))
    for n in (ctx.get("naver_news") or [])[:3]:
        title = clean_display_text(str(n.get("title") or ""))
        items.append(f"[뉴스] {title}")
    if items:
        lines.append("- 주요 뉴스/공시")
        for i, line in enumerate(items, 1):
            lines.append(f"  {i}. {line}")


def _append_stock_detail(lines: list[str], stock: dict[str, Any]) -> None:
    m = stock.get("metrics") or {}
    dq = m.get("data_status") or m.get("data_quality") or "-"
    action = stock.get("action", "")
    level = stock.get("severity_label") or stock.get("remove_level") or ""
    lines.append(f"### {stock.get('symbol')} ({stock.get('ticker')})")
    lines.append("")
    lines.append(f"- 판단: {level or action}")
    one = str(stock.get("one_line") or "").strip()
    if one:
        lines.append(f"- 한 줄: {one}")
    lines.append(
        f"- 5일 {m.get('return_5d', 'N/A')}%, RS {m.get('sector_relative_strength', 'N/A')}, "
        f"데이터 {dq}"
    )
    _append_stock_news_block(lines, stock)
    lines.append("")


def build_markdown_report(
    *,
    as_of_date: str,
    metrics: list[dict[str, Any]],
    sector_mood: dict[str, str],
    judgment: dict[str, Any],
) -> str:
    stocks = judgment.get("stocks") or []
    lines = [
        f"# 주간 관심종목 재평가",
        "",
        f"기준일: {as_of_date}",
        "",
        f"> {judgment.get('summary', '')}",
        "",
        "## 요약",
        "",
        (
            f"- 핵심 유지 {judgment.get('keep_count', 0)}"
            f" / 관찰 약화 {judgment.get('weaken_count', 0)}"
            f" / 주의 관찰 {judgment.get('caution_count', 0)}"
            f" / 제외 후보 {judgment.get('remove_count', 0)}"
            f" (강한 {judgment.get('strong_remove_count', 0)}"
            f" / 검토 {judgment.get('review_remove_count', 0)})"
            f" / 데이터 확인 {judgment.get('data_check_count', 0)}"
        ),
        "",
    ]

    def _group(action: str, **extra: Any) -> list[dict[str, Any]]:
        out = [s for s in stocks if s.get("action") == action]
        for k, v in extra.items():
            if k == "reason_code":
                out = [s for s in out if s.get("reason_code") == v]
            elif k == "reason_code_ne":
                out = [s for s in out if s.get("reason_code") != v]
            elif k == "remove_level":
                out = [s for s in out if s.get("remove_level") == v]
            elif k == "remove_level_ne":
                out = [s for s in out if s.get("remove_level") != v]
        return sorted(out, key=lambda x: -int(x.get("priority_score") or 0))

    def _section(title: str, group: list[dict[str, Any]]) -> None:
        lines.append(title)
        lines.append("")
        if not group:
            lines.append("_해당 없음_")
            lines.append("")
            return
        for s in group:
            _append_stock_detail(lines, s)

    _section("## 핵심 유지", _group("keep"))
    _section("## 관찰 약화", _group("weaken", reason_code_ne=REASON_CAUTION))
    _section("## 주의 관찰", _group("weaken", reason_code=REASON_CAUTION))
    lines.append("## 제외 후보")
    lines.append("")
    strong = _group("remove_candidate", remove_level=REMOVE_LEVEL_STRONG)
    review = _group("remove_candidate", remove_level_ne=REMOVE_LEVEL_STRONG)
    if strong:
        lines.append("### 강한 제외")
        lines.append("")
        for s in strong:
            _append_stock_detail(lines, s)
    if review:
        lines.append("### 제외 검토")
        lines.append("")
        for s in review:
            _append_stock_detail(lines, s)
    if not strong and not review:
        lines.append("_해당 없음_")
        lines.append("")
    _section("## 데이터 확인 필요", _group("data_check_needed"))

    lines.append("## 종목별 뉴스·공시 이슈")
    lines.append("")
    for s in sorted(stocks, key=lambda x: str(x.get("symbol") or "")):
        ctx = s.get("news_context") or {}
        if not (ctx.get("naver_news") or ctx.get("dart_disclosures")):
            continue
        _append_stock_detail(lines, s)

    lines.append("## 다음 주 체크포인트")
    lines.append("")
    for point in build_next_week_checkpoints(judgment, sector_mood):
        lines.append(f"- {point}")
    lines.append("")

    lines.extend(["## 섹터 분위기", ""])
    for sector, mood in sector_mood.items():
        note = (judgment.get("sector_notes") or {}).get(sector, "")
        lines.append(f"- **{sector}** ({MOOD_KO.get(mood, mood)}): {note or '-'}")
    lines.extend(
        [
            "",
            "## 메트릭 요약",
            "",
            "| 종목 | 데이터 | 5일수익 | TV증가 | Slack발송 |",
            "|------|--------|---------|--------|-------------|",
        ]
    )
    for row in metrics:
        lines.append(
            f"| {row.get('symbol')} | {row.get('data_status', row.get('data_quality'))} | "
            f"{row.get('return_5d')}% | "
            f"{round(float(row.get('tv_growth_5d_vs_10d') or 0) * 100, 1)}% | "
            f"{row.get('recent_slack_sent_count')} |"
        )
    lines.append("")
    lines.append("_kr_watchlist.json 자동 반영 없음 (제안서만)._")
    return "\n".join(lines)


def _stock_slack_line(stock: dict[str, Any]) -> str:
    line = str(stock.get("one_line") or "").strip()
    if line:
        return line
    reasons = stock.get("reasons") or []
    return str(reasons[0]) if reasons else ""


def _append_stock_slack_entry(lines: list[str], stock: dict[str, Any]) -> None:
    symbol = stock.get("symbol")
    lines.append(f"• {symbol} — {_stock_slack_line(stock)}")
    issue = format_slack_issue_line(stock.get("news_context"))
    if issue:
        lines.append(f"  이슈: {issue}")


def _priority_desc(stock: dict[str, Any]) -> tuple[int, str]:
    return (-int(stock.get("priority_score") or 0), str(stock.get("ticker") or ""))


def _is_caution_watch(stock: dict[str, Any]) -> bool:
    """판단 단계 reason_code 우선, 없으면 메트릭 휴리스틱."""
    if stock.get("reason_code") == REASON_CAUTION:
        return True
    metrics = stock.get("metrics") or {}
    ret5 = float(metrics.get("return_5d") or 0)
    rs = float(metrics.get("sector_relative_strength") or 50)
    priority = int(stock.get("priority_score") or 50)
    return priority <= 39 or (ret5 < -2 and rs < 40)


def _remove_sort_key(stock: dict[str, Any]) -> tuple[int, str]:
    """제외 후보 — severity 낮을수록(약세) 먼저."""
    return (int(stock.get("severity_score") or 50), str(stock.get("ticker") or ""))


def _partition_slack_groups(
    stocks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    keep = [s for s in stocks if s.get("action") == "keep"]
    remove_all = [s for s in stocks if s.get("action") == "remove_candidate"]
    strong_remove = [
        s for s in remove_all if s.get("remove_level") == REMOVE_LEVEL_STRONG
    ]
    review_remove = [
        s for s in remove_all if s.get("remove_level") != REMOVE_LEVEL_STRONG
    ]
    data_check = [s for s in stocks if s.get("action") == "data_check_needed"]
    weaken_all = [s for s in stocks if s.get("action") == "weaken"]
    caution = [s for s in weaken_all if _is_caution_watch(s)]
    caution_ids = {id(s) for s in caution}
    weaken_mild = [s for s in weaken_all if id(s) not in caution_ids]

    for group in (keep, weaken_mild, caution, strong_remove, review_remove, data_check):
        if group is strong_remove or group is review_remove:
            group.sort(key=_remove_sort_key)
        else:
            group.sort(key=_priority_desc)

    return {
        "keep": keep,
        "weaken": weaken_mild,
        "caution": caution,
        "strong_remove": strong_remove,
        "review_remove": review_remove,
        "remove_candidate": strong_remove + review_remove,
        "data_check_needed": data_check,
    }


def _append_slack_section(
    lines: list[str],
    *,
    title: str,
    subtitle: str,
    stocks: list[dict[str, Any]],
) -> None:
    if not stocks:
        return
    lines.append(title)
    lines.append(f"_{subtitle}_")
    shown = stocks[:SLACK_SECTION_MAX]
    for s in shown:
        _append_stock_slack_entry(lines, s)
    rest = len(stocks) - len(shown)
    if rest > 0:
        lines.append(f"_외 {rest}개_")
    lines.append("")


def _append_remove_tier_lines(
    lines: list[str],
    *,
    label: str,
    stocks: list[dict[str, Any]],
    max_show: int,
    min_show: int = 0,
) -> None:
    """제외 하위 그룹 — 그룹별 cap·초과분 '_외 N개_'."""
    if not stocks:
        return
    lines.append(f"*{label}*")
    limit = min(max_show, len(stocks))
    if min_show > 0:
        limit = max(min_show, limit)
    for s in stocks[:limit]:
        _append_stock_slack_entry(lines, s)
    rest = len(stocks) - limit
    if rest > 0:
        lines.append(f"_외 {rest}개_")


def _append_remove_slack_section(
    lines: list[str],
    *,
    strong: list[dict[str, Any]],
    review: list[dict[str, Any]],
) -> None:
    """제외 후보 — 강한 제외 최대 6, 제외 검토 최대 2(최소 1)."""
    if not strong and not review:
        return
    lines.append("🚫 제외 후보")
    lines.append("_단기 관심종목에서 제외 검토_")
    _append_remove_tier_lines(
        lines,
        label=SEVERITY_LABEL_STRONG,
        stocks=strong,
        max_show=SLACK_STRONG_REMOVE_MAX,
    )
    _append_remove_tier_lines(
        lines,
        label=SEVERITY_LABEL_REVIEW,
        stocks=review,
        max_show=SLACK_REVIEW_REMOVE_MAX,
        min_show=SLACK_REVIEW_REMOVE_MIN if review else 0,
    )
    lines.append("")


def build_slack_text(
    *,
    as_of_date: str,
    judgment: dict[str, Any],
) -> str:
    """매매 판단용 Slack 요약 — 섹션당 최대 8종목, 나머지 '외 N개'."""
    stocks = judgment.get("stocks") or []
    groups = _partition_slack_groups(stocks)
    caution_n = judgment.get("caution_count")
    if caution_n is None:
        caution_n = len(groups["caution"])
    strong_n = judgment.get("strong_remove_count")
    if strong_n is None:
        strong_n = len(groups["strong_remove"])
    review_n = judgment.get("review_remove_count")
    if review_n is None:
        review_n = len(groups["review_remove"])

    lines = [
        f"📋 *주간 관심종목 재평가* ({as_of_date})",
        "",
        "*요약*",
        (
            f"🟢 핵심 유지 {len(groups['keep'])} / "
            f"🟡 관찰 약화 {len(groups['weaken'])} / "
            f"⚠️ 주의 관찰 {caution_n} / "
            f"🚫 제외 {len(groups['remove_candidate'])} "
            f"(강한 {strong_n}·검토 {review_n}) / "
            f"🧪 데이터 확인 {len(groups['data_check_needed'])}"
        ),
        "",
    ]

    for action_key, title, subtitle in SLACK_TRADING_SECTIONS:
        if action_key == "remove_candidate":
            _append_remove_slack_section(
                lines,
                strong=groups["strong_remove"],
                review=groups["review_remove"],
            )
            continue
        _append_slack_section(
            lines,
            title=title,
            subtitle=subtitle,
            stocks=groups[action_key],
        )

    lines.append("_제안서만 생성·watchlist 자동 수정 없음_")
    return "\n".join(lines).strip()


def write_outputs(
    *,
    as_of_date: str,
    metrics: list[dict[str, Any]],
    sector_mood: dict[str, str],
    judgment: dict[str, Any],
) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)

    md_path = REPORT_DIR / f"{as_of_date}.md"
    json_path = PROPOSAL_DIR / f"{as_of_date}.json"

    md_path.write_text(
        build_markdown_report(
            as_of_date=as_of_date,
            metrics=metrics,
            sector_mood=sector_mood,
            judgment=judgment,
        ),
        encoding="utf-8",
    )
    import json

    payload = build_proposal_payload(
        as_of_date=as_of_date, metrics=metrics, judgment=judgment
    )
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return md_path, json_path
