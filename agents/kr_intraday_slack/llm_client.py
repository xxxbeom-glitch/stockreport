"""KR 장중 슬랙 멀티 모델 설정 (환경변수만, 하드코딩 없음)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("kr_intraday.llm")

_DEEPSEEK_SYSTEM = """당신은 한국 주식 장중 관심종목 분석가입니다.
1주 테스트 진입 관점으로만 판단합니다. 추격매수를 권하지 않습니다.
응답은 반드시 JSON 객체 하나만 출력합니다. 마크다운 코드블록 금지.

허용 decision 값 (send_slack=true 가능):
테스트 진입 검토, 예약가 제안, 관찰 강화, 눌림 진입 가능, 수급 반전 감지

금지 decision 값 (send_slack=false):
비추천, 진입 보류, 주의 필요, 추격매수 위험, 거래대금 부족, 수급 약함, 판단 애매, 데이터 부족

금지 표현: 무조건 매수, 지금 사세요, 이 가격에 사세요, 급등 따라가세요"""


def primary_config() -> dict[str, str]:
    """DeepSeek 1차 판단."""
    return {
        "role": "primary",
        "provider": os.getenv("AI_PROVIDER", "deepseek").strip().lower(),
        "model": (
            os.getenv("AI_MODEL", "").strip()
            or os.getenv("DEEPSEEK_MODEL", "").strip()
            or "deepseek-chat"
        ),
        "api_key": os.getenv("DEEPSEEK_API_KEY", "").strip(),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
    }


def social_config() -> dict[str, str]:
    """Grok — 뉴스/X/시장 분위기 보조."""
    return {
        "role": "social",
        "provider": os.getenv("AI_SOCIAL_PROVIDER", "grok").strip().lower(),
        "model": (
            os.getenv("AI_SOCIAL_MODEL", "").strip()
            or os.getenv("GROK_MODEL", "").strip()
            or "grok-3"
        ),
        "api_key": os.getenv("GROK_API_KEY", "").strip(),
        "base_url": os.getenv("GROK_BASE_URL", "https://api.x.ai/v1").strip(),
    }


def summary_config() -> dict[str, str]:
    """Gemini — 슬랙 메시지 문장 정리."""
    return {
        "role": "summary",
        "provider": os.getenv("AI_SUMMARY_PROVIDER", "gemini").strip().lower(),
        "model": (
            os.getenv("AI_SUMMARY_MODEL", "").strip()
            or os.getenv("GEMINI_SUMMARY_MODEL", "").strip()
            or "gemini-1.5-flash"
        ),
        "api_key": os.getenv("GEMINI_API_KEY", "").strip(),
    }


def is_primary_configured() -> bool:
    cfg = primary_config()
    return cfg["provider"] == "deepseek" and bool(cfg["api_key"])


# 하위 호환
is_ai_configured = is_primary_configured
ai_config = primary_config


def is_grok_configured() -> bool:
    cfg = social_config()
    return cfg["provider"] == "grok" and bool(cfg["api_key"])


def is_gemini_configured() -> bool:
    cfg = summary_config()
    return cfg["provider"] == "gemini" and bool(cfg["api_key"])


def aux_models_status() -> dict[str, Any]:
    """파이프라인 시작 시 로그용."""
    grok = social_config()
    gem = summary_config()
    return {
        "primary": {
            "configured": is_primary_configured(),
            "provider": primary_config()["provider"],
            "model": primary_config()["model"],
        },
        "grok": {
            "configured": is_grok_configured(),
            "provider": grok["provider"],
            "model": grok["model"],
        },
        "gemini": {
            "configured": is_gemini_configured(),
            "provider": gem["provider"],
            "model": gem["model"],
        },
    }


def _parse_json_payload(text: str) -> dict[str, Any] | None:
    if not text or not isinstance(text, str):
        return None
    normalized = text.strip()
    normalized = re.sub(r"```json\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"```\s*", "", normalized).strip()
    try:
        parsed = json.loads(normalized)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", normalized, flags=re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def call_primary_json(
    prompt: str,
    *,
    agent: str = "kr_intraday_primary",
) -> tuple[dict[str, Any] | None, str | None]:
    """DeepSeek JSON 판단. 실패 시 더미 없음."""
    cfg = primary_config()
    if cfg["provider"] != "deepseek":
        return None, f"지원하지 않는 AI_PROVIDER: {cfg['provider']}"
    if not cfg["api_key"]:
        return None, "DEEPSEEK_API_KEY 미설정"

    try:
        from openai import OpenAI
    except ImportError as exc:
        return None, f"openai 패키지 없음: {exc}"

    try:
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        response = client.chat.completions.create(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": _DEEPSEEK_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        text = (response.choices[0].message.content or "").strip()
        parsed = _parse_json_payload(text)
        if not parsed:
            logger.error("[%s] JSON 파싱 실패 head=%s", agent, text[:300])
            return None, "LLM 응답 JSON 파싱 실패"
        logger.info("[%s] OK provider=%s model=%s", agent, cfg["provider"], cfg["model"])
        return parsed, None
    except Exception as exc:
        logger.error("[%s] 호출 실패: %s", agent, exc)
        return None, f"LLM API 오류: {exc}"


# 하위 호환
call_llm_json = call_primary_json
