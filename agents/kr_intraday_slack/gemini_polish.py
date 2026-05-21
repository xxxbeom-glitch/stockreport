"""Gemini Polish Agent — Slack 10초 가독 말투 다듬기 (optional)."""

from __future__ import annotations

import logging
import re
from typing import Any

from .constants import FORBIDDEN_PHRASES, slack_display_label
from .purpose import APP_PURPOSE, COMMON_PRINCIPLES, GEMINI_POLISH_PURPOSE
from .llm_client import is_gemini_configured, summary_config
from .constants import SCAN_SLOTS
from .message_tone import (
    compose_sector_summary_message,
    compose_slack_message,
    contains_slack_body_forbidden,
    contains_slack_ellipsis,
    has_new_candidate_stock_shape,
    has_required_slack_shape,
    has_sector_summary_shape,
    is_message_too_long,
    is_message_too_stiff,
    is_new_candidate_stock_too_long,
    is_sector_summary_too_long,
    sanitize_slack_mrkdwn,
)

logger = logging.getLogger("kr_intraday.gemini")

_MAX_RETRIES = 2


def _contains_forbidden(text: str) -> bool:
    if contains_slack_body_forbidden(text):
        return True
    lower = text.lower()
    return any(p in text or p in lower for p in FORBIDDEN_PHRASES)


def _polish_prompt(draft: str, row: dict[str, Any], *, retry_short: bool = False) -> str:
    label = slack_display_label(str(row.get("ai_decision") or row.get("status") or ""))
    extra = ""
    if retry_short:
        extra = """
이전 결과가 너무 길거나 딱딱했습니다. 8~10줄 이내, 짧은 문장만. mrkdwn 구조는 유지."""

    return f"""{APP_PURPOSE}

{GEMINI_POLISH_PURPOSE}

{COMMON_PRINCIPLES}
{extra}

10초 안에 읽히게 말투만 다듬으세요. Slack 구조·줄 수 유지 (최대 5줄):

• {row.get("name")}
현재가: (숫자 그대로, 원 단위 유지)
볼 구간: (숫자 범위 필수, 변경·생략 금지)
이유: (완성 문장 1~2개, 너무 짧지 않게)
주의: (완성 문장 1개)

규칙:
- "매수", "추천", "진입" 표현 금지
- "관찰 구간" → "볼 구간", "신규 후보" → "새 후보"
- RS·모멘텀·저항·수급 같은 어려운 말 피하기 (외국인 매수·거래대금·신고가·실적·공시·뉴스는 가능)
- "취소 조건" 단어 금지
- "테스트", "드라이런", "검증" 금지
- 리포트체·숫자 나열 금지
- 가격·종목명·구간 숫자는 변경 금지
- 줄임표(.../…) 금지, 글자 수로 자르지 말 것
- JSON 없이 메시지 본문만

초안:
---
{draft}
---"""


def _retry_shorten_prompt(draft: str, row: dict[str, Any], reason: str) -> str:
    return f"""아래 슬랙 메시지를 더 짧게 다시 써 주세요. ({reason})

- 구조 유지 (• 종목명 / 현재가 / 볼 구간 / 이유 / 주의), 최대 5줄
- "매수", "추천", "진입" 금지
- 줄임표 금지, 가격 숫자 유지

---
{draft}
---"""


def _call_gemini(prompt: str, model: str) -> str | None:
    from agents.gemini_client import generate_gemini_text

    return generate_gemini_text(
        prompt,
        agent="kr_intraday_gemini_polish",
        model=model,
    )


def _accept_or_none(text: str, draft: str, row: dict[str, Any]) -> str | None:
    if not text or not text.strip():
        return None
    cleaned = sanitize_slack_mrkdwn(text.strip())
    if _contains_forbidden(cleaned) or contains_slack_ellipsis(cleaned):
        return None
    if not has_required_slack_shape(cleaned):
        return None
    if has_new_candidate_stock_shape(cleaned):
        if is_new_candidate_stock_too_long(cleaned):
            return None
    elif is_message_too_long(cleaned):
        return None
    return cleaned


def polish_slack_message(
    draft: str,
    row: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    Returns (final_message, meta).
    API 실패·금지 표현·형식 불일치 시 message_tone 재조립.
    """
    meta: dict[str, Any] = {
        "provider": summary_config()["provider"],
        "model": summary_config()["model"],
    }

    if not draft.strip():
        meta["status"] = "skipped"
        meta["reason"] = "초안 없음"
        return draft, meta

    if not is_gemini_configured():
        meta["status"] = "skipped"
        meta["reason"] = "GEMINI_API_KEY 미설정"
        logger.info("[%s] Gemini skip: %s", row.get("ticker"), meta["reason"])
        return draft, meta

    cfg = summary_config()
    if cfg["provider"] != "gemini":
        meta["status"] = "skipped"
        meta["reason"] = f"AI_SUMMARY_PROVIDER 미지원: {cfg['provider']}"
        return draft, meta

    try:
        model = cfg["model"]
        prompt = _polish_prompt(draft, row)
        polished = _call_gemini(prompt, model)
        accepted = _accept_or_none(polished or "", draft, row)

        attempts = 0
        while accepted and is_message_too_stiff(accepted) and attempts < _MAX_RETRIES:
            attempts += 1
            logger.info("[%s] Gemini stiff → shorten retry %d", row.get("ticker"), attempts)
            retry = _call_gemini(
                _retry_shorten_prompt(accepted, row, "말투가 딱딱함"),
                model,
            )
            accepted = _accept_or_none(retry or "", draft, row) or accepted

        while accepted and is_message_too_long(accepted) and attempts < _MAX_RETRIES:
            attempts += 1
            logger.info("[%s] Gemini long → shorten retry %d", row.get("ticker"), attempts)
            retry = _call_gemini(
                _retry_shorten_prompt(accepted, row, "메시지가 김"),
                model,
            )
            accepted = _accept_or_none(retry or "", draft, row) or accepted

        if accepted and not is_message_too_stiff(accepted):
            meta["status"] = "ok"
            meta["retries"] = attempts
            logger.info("[%s %s] Gemini polish OK", row.get("ticker"), row.get("name"))
            return accepted, meta

        local = compose_slack_message(row)
        if local and has_required_slack_shape(local) and not _contains_forbidden(local):
            meta["status"] = "ok_local"
            meta["reason"] = "Gemini 미수용 → message_tone 재조립"
            logger.info("[%s] %s", row.get("ticker"), meta["reason"])
            return local, meta

        meta["status"] = "fallback"
        meta["reason"] = "Gemini 미수용, 로컬 재조립 실패"
        return draft, meta

    except Exception as exc:
        meta["status"] = "fallback"
        meta["reason"] = f"Gemini API 오류: {exc}"
        logger.warning("[%s] Gemini fallback: %s", row.get("ticker"), meta["reason"])
        local = compose_slack_message(row)
        if local and not _contains_forbidden(local):
            meta["status"] = "ok_local"
            meta["reason"] = f"API 오류 후 message_tone 재조립: {exc}"
            return local, meta
        return sanitize_slack_mrkdwn(draft), meta


def _sector_summary_polish_prompt(draft: str, *, slot: str) -> str:
    clock = SCAN_SLOTS.get(slot, (slot, ""))[0]
    return f"""{APP_PURPOSE}

{GEMINI_POLISH_PURPOSE}

{COMMON_PRINCIPLES}

장중 슬랙 *섹터별 요약* — 10초 가독, 말투만 다듬기.

반드시 유지할 구조:
- 📊 *장중 관심종목 스캔* 헤더
- 기준 슬롯: {clock}
- 스캔 대상: 관심종목 N개
- 구분선 ――――――――――
- 5개 섹터명 굵게 (*반도체 소재* 등) — 순서·이름 변경 금지
- 각 섹터: "진입 검토 종목 N개" (0이면 없음, 1~2개 가능 — 섹터당 1개 고정 아님) 또는 "진입 검토 종목 없음"
- 종목 카드: 📌 *종목명*, *현재가*, *진입 후보 구간*, 설명 2~4문장, • *1주 기준*, • *경고* (섹터에 여러 카드면 순서·개수 유지)

규칙:
- "진입 후보 구간" = 1주 기준 매수 타이밍을 노릴 가격대 (예: 119,000원 ~ 122,000원)
- "경고" = 매수가 아님, 구간 무효·오늘은 넘기기 기준
- "취소 조건" 금지 → "• *경고*"
- "테스트", "드라이런", "검증" 금지
- 완성 문장만, 줄임표(.../…) 금지
- 섹터·구분선·종목 가격 숫자는 변경 금지
- JSON 없이 본문만

초안:
---
{draft}
---"""


def _accept_sector_summary(text: str, draft: str) -> str | None:
    if not text or not text.strip():
        return None
    cleaned = sanitize_slack_mrkdwn(text.strip())
    if _contains_forbidden(cleaned) or contains_slack_ellipsis(cleaned):
        return None
    if not has_sector_summary_shape(cleaned):
        return None
    if is_sector_summary_too_long(cleaned):
        return None
    return cleaned


def polish_sector_summary_message(
    draft: str,
    send_rows: list[dict[str, Any]],
    *,
    slot: str,
    scanned: int = 25,
) -> tuple[str, dict[str, Any]]:
    """섹터 요약 전체 1건 polish (구조 깨지면 로컬 재조립)."""
    meta: dict[str, Any] = {
        "provider": summary_config()["provider"],
        "model": summary_config()["model"],
        "scope": "sector_summary",
    }

    if not draft.strip():
        meta["status"] = "skipped"
        meta["reason"] = "초안 없음"
        return draft, meta

    if not is_gemini_configured():
        meta["status"] = "skipped"
        meta["reason"] = "GEMINI_API_KEY 미설정"
        return draft, meta

    cfg = summary_config()
    if cfg["provider"] != "gemini":
        meta["status"] = "skipped"
        meta["reason"] = f"AI_SUMMARY_PROVIDER 미지원: {cfg['provider']}"
        return draft, meta

    try:
        from utils.safe_stdio import ensure_stdio

        ensure_stdio()
    except ImportError:
        pass

    try:
        model = cfg["model"]
        polished = _call_gemini(_sector_summary_polish_prompt(draft, slot=slot), model)
        accepted = _accept_sector_summary(polished or "", draft)

        if accepted and not is_message_too_stiff(accepted):
            meta["status"] = "ok"
            logger.info("[KR INTRADAY] Gemini sector summary polish OK")
            return accepted, meta

        local = compose_sector_summary_message(
            slot_clock=SCAN_SLOTS.get(slot, (slot, ""))[0],
            scanned=scanned or _scanned_from_draft(draft),
            send_rows=send_rows,
        )
        if local and has_sector_summary_shape(local) and not _contains_forbidden(local):
            meta["status"] = "ok_local"
            meta["reason"] = "Gemini 미수용 → 섹터 요약 재조립"
            return local, meta

        meta["status"] = "fallback"
        meta["reason"] = "Gemini 미수용"
        return draft, meta
    except Exception as exc:
        meta["status"] = "fallback"
        meta["reason"] = f"Gemini API 오류: {exc}"
        local = compose_sector_summary_message(
            slot_clock=SCAN_SLOTS.get(slot, (slot, ""))[0],
            scanned=scanned or _scanned_from_draft(draft),
            send_rows=send_rows,
        )
        if local and not _contains_forbidden(local):
            meta["status"] = "ok_local"
            return local, meta
        return sanitize_slack_mrkdwn(draft), meta


def _scanned_from_draft(draft: str) -> int:
    m = re.search(r"스캔 대상:\s*관심종목\s*(\d+)\s*개", draft)
    if m:
        return int(m.group(1))
    return 25
