"""MVP 4-2 — 신규 후보 에이전트 투표 (가격·거래·뉴스·위험·섹터)."""

from __future__ import annotations

from typing import Any, Literal

_OVERHEAT_5D_PCT = 15.0
_DISTANCE_OK_PCT = 8.0
_DISTANCE_RED_MAX_PCT = 12.0

Vote = Literal["approve", "hold", "reject"]

AGENT_KEYS: tuple[str, ...] = ("price", "volume", "news", "risk", "sector")

VOTE_ICONS: dict[str, str] = {
    "approve": "✅",
    "hold": "△",
    "reject": "⚠️",
}

CHECK_LABELS: dict[str, str] = {
    "price": "가격",
    "volume": "거래",
    "news": "뉴스",
    "risk": "위험",
}

FINAL_OPINION_LABELS: dict[str, str] = {
    "green": "지금 볼만함",
    "yellow": "조금 기다림",
    "red": "오늘은 패스",
    "exclude": "표시 제외",
}


def _vote_record(vote: Vote, reason: str) -> dict[str, str]:
    return {"vote": vote, "reason": reason.strip()}


def vote_price_agent(candidate: dict[str, Any], metrics: dict[str, Any]) -> dict[str, str]:
    ret = float(metrics.get("return_5d_pct") or candidate.get("return_5d_pct") or 0)
    near = bool(metrics.get("near_high") or candidate.get("near_high"))
    if ret >= 3.0 and near:
        return _vote_record("approve", "최근 가격 흐름이 좋습니다.")
    if ret > 0:
        return _vote_record("hold", "가격 흐름은 나쁘지 않지만 더 확인이 필요합니다.")
    return _vote_record("reject", "최근 가격 흐름이 약합니다.")


def vote_volume_agent(candidate: dict[str, Any], metrics: dict[str, Any]) -> dict[str, str]:
    if metrics.get("tv_increase") or candidate.get("tv_increase"):
        return _vote_record("approve", "거래가 평소보다 늘었습니다.")
    latest = float(metrics.get("latest_trading_value") or 0)
    if latest >= 1_000_000_000:
        return _vote_record("hold", "거래는 있지만 뚜렷한 증가는 아닙니다.")
    return _vote_record("reject", "거래가 아직 충분하지 않습니다.")


def vote_news_agent(
    candidate: dict[str, Any],
    metrics: dict[str, Any],
    *,
    news_context: dict[str, Any] | None = None,
) -> dict[str, str]:
    del metrics
    has_news = bool(candidate.get("has_news"))
    has_dart = bool(candidate.get("has_dart"))
    ctx = news_context or {}
    news_items = ctx.get("news") if isinstance(ctx.get("news"), list) else []
    dart_items = ctx.get("dart_disclosures") or ctx.get("disclosures") or []
    if not isinstance(dart_items, list):
        dart_items = []

    if has_dart:
        return _vote_record("approve", "관련 공시가 있어 흐름을 볼 만합니다.")
    if has_news and len(news_items) >= 2:
        return _vote_record("approve", "관련 뉴스가 있어 오늘 계속 볼 만합니다.")
    if has_news:
        return _vote_record("hold", "관련 뉴스는 있지만 강한 이슈는 아닙니다.")
    if has_dart:
        return _vote_record("hold", "공시는 있지만 영향은 더 봐야 합니다.")
    return _vote_record("hold", "뚜렷한 뉴스·공시는 아직 없습니다.")


def vote_risk_agent(candidate: dict[str, Any], metrics: dict[str, Any]) -> dict[str, str]:
    ret = float(metrics.get("return_5d_pct") or candidate.get("return_5d_pct") or 0)
    dist = candidate.get("distance_pct")
    if dist is None:
        dist = metrics.get("distance_pct")
    try:
        dist_f = float(dist) if dist is not None else None
    except (TypeError, ValueError):
        dist_f = None

    band = str(candidate.get("distance_band") or "")

    if ret >= _OVERHEAT_5D_PCT:
        return _vote_record("reject", "단기간에 많이 올라 부담이 큽니다.")
    if band == "exclude" or (dist_f is not None and dist_f > _DISTANCE_RED_MAX_PCT):
        return _vote_record("reject", "가격이 볼 구간과 너무 멉니다.")
    if band == "red_only" or (dist_f is not None and dist_f > _DISTANCE_OK_PCT):
        return _vote_record("hold", "가격이 조금 높아 바로 보기엔 부담이 있습니다.")
    return _vote_record("approve", "가격 부담이 크지 않습니다.")


def vote_sector_agent(
    candidate: dict[str, Any],
    metrics: dict[str, Any],
    *,
    sector_context: dict[str, Any] | None = None,
) -> dict[str, str]:
    del metrics
    sector = str(candidate.get("sector_name") or "").strip()
    ctx = (sector_context or {}).get(sector) if sector_context else None
    if not ctx or not ctx.get("available"):
        return _vote_record("hold", "섹터 흐름은 추가 확인이 필요합니다.")

    ret = float(candidate.get("return_5d_pct") or 0)
    avg_ret = float(ctx.get("avg_return_5d") or 0)
    tv_ratio = float(ctx.get("tv_increase_ratio") or 0)
    pos_ratio = float(ctx.get("positive_ratio") or 0)

    if ret >= avg_ret and tv_ratio >= 0.5 and pos_ratio >= 0.5:
        return _vote_record("approve", "같은 섹터 흐름도 나쁘지 않습니다.")
    if ret < 0 and avg_ret < 0:
        return _vote_record("reject", "섹터 흐름이 함께 약합니다.")
    if ret >= avg_ret:
        return _vote_record("hold", "섹터 흐름은 괜찮지만 종목별로 더 봐야 합니다.")
    return _vote_record("hold", "섹터 흐름은 추가 확인이 필요합니다.")


def build_sector_context(scored: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """섹터별 평균 흐름 — 후보 2개 이상일 때만 available."""
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for row in scored:
        sector = str(row.get("sector_name") or "").strip() or "기타"
        by_sector.setdefault(sector, []).append(row)

    out: dict[str, dict[str, Any]] = {}
    for sector, rows in by_sector.items():
        if len(rows) < 2:
            out[sector] = {"available": False}
            continue
        rets = [float(r.get("return_5d_pct") or 0) for r in rows]
        tv_flags = [1 if r.get("tv_increase") else 0 for r in rows]
        out[sector] = {
            "available": True,
            "count": len(rows),
            "avg_return_5d": round(sum(rets) / len(rets), 2),
            "tv_increase_ratio": round(sum(tv_flags) / len(tv_flags), 2),
            "positive_ratio": round(sum(1 for x in rets if x > 0) / len(rets), 2),
        }
    return out


def run_candidate_agent_votes(
    candidate: dict[str, Any],
    metrics: dict[str, Any],
    *,
    news_context: dict[str, Any] | None = None,
    sector_context: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, str]]:
    """5개 에이전트 투표."""
    return {
        "price": vote_price_agent(candidate, metrics),
        "volume": vote_volume_agent(candidate, metrics),
        "news": vote_news_agent(candidate, metrics, news_context=news_context),
        "risk": vote_risk_agent(candidate, metrics),
        "sector": vote_sector_agent(candidate, metrics, sector_context=sector_context),
    }


def summarize_votes(agent_votes: dict[str, dict[str, str]]) -> dict[str, int]:
    summary = {"approve": 0, "hold": 0, "reject": 0}
    for record in agent_votes.values():
        vote = str(record.get("vote") or "hold")
        if vote in summary:
            summary[vote] += 1
    return summary


def apply_vote_to_tier(
    candidate: dict[str, Any],
    vote_summary: dict[str, int],
    agent_votes: dict[str, dict[str, str]],
) -> tuple[str, str]:
    """
    투표 합산 → 최종 티어 (green/yellow/red/exclude).
    risk reject면 green 불가.
    reject 2개 이상 → red.
    """
    approve = int(vote_summary.get("approve") or 0)
    reject = int(vote_summary.get("reject") or 0)
    risk_vote = str(agent_votes.get("risk", {}).get("vote") or "hold")

    if reject >= 2:
        tier = "red"
    elif approve >= 3 and reject == 0:
        tier = "green"
    elif approve >= 2 and reject <= 1:
        tier = "yellow"
    elif approve <= 1:
        tier = "red"
    else:
        tier = "yellow"

    if tier == "green" and risk_vote == "reject":
        tier = "yellow"

    if str(candidate.get("distance_band") or "") == "exclude" and tier == "green":
        tier = "yellow"

    opinion = FINAL_OPINION_LABELS.get(tier, "조금 기다림")
    return tier, opinion


def format_agent_check_line(agent_votes: dict[str, dict[str, str]]) -> str:
    """체크: 가격 ✅ / 거래 ✅ / 뉴스 △ / 위험 괜찮음"""
    parts: list[str] = []
    for key in ("price", "volume", "news"):
        vote = str(agent_votes.get(key, {}).get("vote") or "hold")
        parts.append(f"{CHECK_LABELS[key]} {VOTE_ICONS.get(vote, '△')}")

    risk_vote = str(agent_votes.get("risk", {}).get("vote") or "hold")
    if risk_vote == "approve":
        risk_txt = "위험 괜찮음"
    elif risk_vote == "reject":
        risk_txt = "위험 ⚠️"
    else:
        risk_txt = "위험 주의"

    parts.append(risk_txt)
    return "체크: " + " / ".join(parts)


def build_reason_from_votes(
    candidate: dict[str, Any],
    agent_votes: dict[str, dict[str, str]],
) -> str:
    """에이전트 찬성 근거로 이유 1~2문장."""
    parts: list[str] = []
    price_v = agent_votes.get("price", {}).get("vote")
    vol_v = agent_votes.get("volume", {}).get("vote")
    news_v = agent_votes.get("news", {}).get("vote")

    if price_v == "approve" and vol_v == "approve":
        parts.append("최근 가격 흐름이 좋고 거래도 평소보다 늘었습니다.")
    elif price_v == "approve":
        parts.append("최근 가격 흐름이 좋습니다.")
    elif vol_v == "approve":
        parts.append("거래가 평소보다 늘었습니다.")
    elif price_v != "reject":
        parts.append("흐름은 나쁘지 않지만 아직 확실한 이슈는 부족합니다.")

    if news_v == "approve":
        parts.append("관련 이슈도 있어 오늘 계속 볼 만합니다.")
    elif news_v == "hold" and (candidate.get("has_news") or candidate.get("has_dart")):
        parts.append("관련 소식은 있지만 영향은 더 봐야 합니다.")

    risk_v = agent_votes.get("risk", {}).get("vote")
    if risk_v == "hold" and len(parts) < 2:
        parts.append("가격도 볼 구간보다 조금 높은 편입니다.")
    if risk_v == "reject" and len(parts) < 2:
        parts.append("가격이 볼 구간과 멀어 오늘은 패스합니다.")

    if not parts:
        parts.append("오늘 장에서 다시 흐름을 확인할 만합니다.")
    return " ".join(parts[:2])


def enrich_candidate_with_votes(
    row: dict[str, Any],
    metrics: dict[str, Any],
    *,
    news_context: dict[str, Any] | None = None,
    sector_context: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """후보 행에 agent_votes·vote_summary·최종 tier 반영."""
    agent_votes = run_candidate_agent_votes(
        row,
        metrics,
        news_context=news_context,
        sector_context=sector_context,
    )
    vote_summary = summarize_votes(agent_votes)
    tier, final_opinion = apply_vote_to_tier(row, vote_summary, agent_votes)

    out = {**row}
    out["score_tier"] = out.get("tier")
    out["agent_votes"] = agent_votes
    out["vote_summary"] = vote_summary
    out["final_opinion"] = final_opinion
    out["tier"] = tier
    out["agent_check_line"] = format_agent_check_line(agent_votes)
    out["ai_reason"] = build_reason_from_votes(out, agent_votes)

    if tier == "red":
        out["ai_cancel_condition"] = "무리해서 따라가지 않는 편이 좋습니다."
    elif tier == "yellow":
        out["ai_cancel_condition"] = (
            "아래 구간으로 내려올 때 다시 확인하는 게 좋습니다."
        )
    else:
        out["ai_cancel_condition"] = (
            "너무 급하게 따라가기보다는 살짝 눌리는지 보는 게 좋습니다."
        )

    return out
