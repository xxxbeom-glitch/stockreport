"""Grok 보조 — 뉴스/X/시장 분위기 (optional, 발송 결정 변경 없음)."""

from __future__ import annotations

import json
import logging
from typing import Any

from .constants import SCAN_SLOTS
from .llm_client import is_grok_configured, social_config

logger = logging.getLogger("kr_intraday.grok")


def _grok_prompt(row: dict[str, Any], sector_mood: dict[str, str], *, slot: str) -> str:
    clock, label = SCAN_SLOTS.get(slot, (slot, slot))
    return f"""한국 주식 장중 보조 분석 (X/뉴스 맥락만, 매수 추천 금지).

시간: {clock} ({label})
섹터 분위기: {json.dumps(sector_mood, ensure_ascii=False)}

종목: {row.get("name")} ({row.get("ticker")})
섹터: {row.get("sector_name")}
주요사업: {row.get("business")}
현재가: {row.get("current_price_fmt")}
DeepSeek 1차 판단(참고, 변경하지 말 것): {row.get("ai_decision")} / send_slack={row.get("ai_send_slack")}

이 종목이 지금 왜 언급되는지, X·뉴스·시장 분위기를 보조 요약하세요.
슬랙 발송 여부는 결정하지 마세요.

JSON만 응답:
{{
  "mention_summary": "2~3문장 요약",
  "why_now": "지금 주목되는 이유 1~2문장",
  "sector_issue": "섹터·이슈 1문장",
  "x_sentiment": "positive|neutral|negative|unknown"
}}"""


def fetch_grok_context(
    row: dict[str, Any],
    sector_mood: dict[str, str],
    *,
    slot: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Grok X 검색 보조. Returns (context_dict, error).
    키 없거나 실패 시 (None, reason) — 더미 없음.
    """
    if not is_grok_configured():
        return None, "GROK_API_KEY 미설정 — Grok skip"

    cfg = social_config()
    if cfg["provider"] != "grok":
        return None, f"AI_SOCIAL_PROVIDER 미지원: {cfg['provider']}"

    try:
        from agents.grok_client import grok_x_search_json

        parsed, meta = grok_x_search_json(
            _grok_prompt(row, sector_mood, slot=slot),
            agent="kr_intraday_grok_social",
            max_output_tokens=800,
            model=cfg["model"],
        )
        if not parsed:
            err = str(meta.get("error") or "Grok JSON 파싱 실패")
            raw = meta.get("raw_text")
            if raw:
                logger.warning("[%s] Grok raw: %s", row.get("ticker"), raw[:200])
            return None, err

        ctx = {
            "mention_summary": str(parsed.get("mention_summary", "")).strip(),
            "why_now": str(parsed.get("why_now", "")).strip(),
            "sector_issue": str(parsed.get("sector_issue", "")).strip(),
            "x_sentiment": str(parsed.get("x_sentiment", "unknown")).strip(),
            "grok_model": cfg["model"],
            "grok_meta": {k: v for k, v in meta.items() if k != "raw_text"},
        }
        logger.info(
            "[%s %s] Grok OK sentiment=%s",
            row.get("ticker"),
            row.get("name"),
            ctx.get("x_sentiment"),
        )
        return ctx, None
    except Exception as exc:
        logger.warning("[%s] Grok skip: %s", row.get("ticker"), exc)
        return None, f"Grok API 오류: {exc}"


def enrich_rows_with_grok(
    rows: list[dict[str, Any]],
    sector_mood: dict[str, str],
    *,
    slot: str,
    only_send_slack: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    DeepSeek 판단 후 Grok 보조 필드 병합.
    send_slack / decision 은 변경하지 않음.
    """
    notes: list[str] = []
    if not is_grok_configured():
        notes.append("Grok optional skip: GROK_API_KEY 미설정")
        logger.info("[KR INTRADAY] %s", notes[-1])
        return rows, notes

    out: list[dict[str, Any]] = []
    for row in rows:
        merged = dict(row)
        if only_send_slack and not row.get("ai_send_slack"):
            out.append(merged)
            continue
        ctx, err = fetch_grok_context(row, sector_mood, slot=slot)
        if err:
            notes.append(f"[{row.get('name')}] Grok: {err}")
            merged["grok_status"] = "skipped"
            merged["grok_skip_reason"] = err
        elif ctx:
            merged["grok_status"] = "ok"
            merged["grok_mention_summary"] = ctx.get("mention_summary", "")
            merged["grok_why_now"] = ctx.get("why_now", "")
            merged["grok_sector_issue"] = ctx.get("sector_issue", "")
            merged["grok_x_sentiment"] = ctx.get("x_sentiment", "")
            merged["grok_context"] = ctx
        out.append(merged)

    ok = sum(1 for r in out if r.get("grok_status") == "ok")
    logger.info("[KR INTRADAY] Grok enrich ok=%d/%d", ok, len([r for r in rows if not only_send_slack or r.get("ai_send_slack")]))
    return out, notes
