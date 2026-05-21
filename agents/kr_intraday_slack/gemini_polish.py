"""Gemini 보조 — 슬랙 메시지 말투 다듬기 (optional)."""

from __future__ import annotations

import logging
from typing import Any

from .constants import FORBIDDEN_PHRASES, slack_display_label
from .llm_client import is_gemini_configured, summary_config
from .message_tone import (
    compose_slack_message,
    contains_slack_body_forbidden,
    has_required_slack_shape,
    is_message_too_long,
    is_message_too_stiff,
)

logger = logging.getLogger("kr_intraday.gemini")

_MAX_RETRIES = 2


def _contains_forbidden(text: str) -> bool:
    if contains_slack_body_forbidden(text):
        return True
    lower = text.lower()
    return any(p in text or p in lower for p in FORBIDDEN_PHRASES)


def _polish_prompt(draft: str, row: dict[str, Any], *, retry_short: bool = False) -> str:
    extra = ""
    if retry_short:
        extra = """
이전 결과가 너무 길거나 딱딱했습니다. 이번엔 반드시 9줄 이내, 짧은 문장만 사용하세요.
"판단:", "진입 관점:", "활발", "데이터 불충분", 숫자 나열 금지."""

    return f"""한국 주식 장중 슬랙 알림입니다. 투자자가 바로 읽을 수 있게 말투만 다듬어 주세요.
{extra}

출력 구조 (줄 수·순서 유지, 6~9줄 권장):
[{slack_display_label(str(row.get("ai_decision") or row.get("status") or ""))}] 종목명

현재가: (그대로)
예약가 후보: (그대로)

지금 이 종목은 ~ 흐름입니다. (1~2문장, 짧게)
다만 바로 따라가기보다는, 예약가 구간까지 눌리는지 보는 게 좋아 보입니다.

1주 기준이라면 이 구간에서만 진입을 검토하고,
아래 취소 조건이 나오면 오늘은 넘기는 쪽이 안전합니다.

취소 조건:
(한 줄)

말투 규칙:
- 리포트/로그체 금지 ("섹터 증대", "활발", "데이터 불충분" 같은 표현 쓰지 않기)
- "매수하세요", "무조건", "급등 추격" 금지
- "테스트", "드라이런", "검증" 단어 금지
- "진입 검토", "눌림 확인", "오늘은 넘기기", "1주 기준" 같은 쉬운 말
- X/이슈 맥락은 있으면 한 줄만 ("이슈:" 로 짧게)
- 가격·종목명·예약가 숫자는 바꾸지 않음
- JSON 없이 메시지 본문만 출력

종목: {row.get("name")}

초안:
---
{draft}
---"""


def _retry_shorten_prompt(draft: str, row: dict[str, Any], reason: str) -> str:
    return f"""아래 슬랙 메시지를 더 짧고 자연스럽게 다시 써 주세요. ({reason})

- 전체 9줄 이내
- 문장은 짧게, 대화체
- 구조: [제목] 종목 / 현재가 / 예약가 / 왜 볼만한지 1~2줄 / 눌림 확인 1줄 / 1주 기준 2줄 / 취소 조건 1줄
- "테스트", "드라이런", "검증" 금지
- 딱딱한 표현·숫자 나열 줄이기
- 가격 숫자는 유지

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
    cleaned = text.strip()
    if _contains_forbidden(cleaned):
        return None
    if not has_required_slack_shape(cleaned):
        return None
    if is_message_too_long(cleaned):
        return None
    return cleaned


def polish_slack_message(
    draft: str,
    row: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    Returns (final_message, meta).
    API 실패·금지 표현만 draft fallback. 딱딱/길면 Gemini 재시도.
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

    # 초안이 이미 자연스러우면 Gemini 생략 가능 — 항상 polish 시도는 유지
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

        # Gemini 실패/거부 시 로컬 템플릿으로 재조립 (draft 원문보다 짧은 말투)
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
        return draft, meta
