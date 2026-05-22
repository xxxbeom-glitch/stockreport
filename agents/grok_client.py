"""Grok API client with real-time X (Twitter) search via x.ai Responses API.

- ``chat.completions`` without tools: X 실시간 검색 OFF
- ``search_parameters`` / ``live_search``: HTTP 410 (deprecated)
- ``responses.create`` + ``tools=[{"type": "x_search"}]``: X 실시간 검색 ON
"""

from __future__ import annotations

from typing import Any

import config
from utils.helpers import safe_json_parse

GROK_X_SEARCH_TOOL: list[dict[str, str]] = [{"type": "x_search"}]
GROK_WEB_X_SEARCH_TOOLS: list[dict[str, str]] = [
    {"type": "web_search"},
    {"type": "x_search"},
]


def _tool_usage_details(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return {}
    details = getattr(usage, "server_side_tool_usage_details", None)
    if isinstance(details, dict):
        return {k: int(v or 0) for k, v in details.items()}
    return {}

X_SEARCH_NOISE_RULES: str = """
X(트위터) 데이터 분석 시 반드시 지켜야 할 규칙:
1. 공식 계정 (언론사, 증권사, 기업 IR) 위주로 해석
2. "단독", "확실함", "~카더라" 등 비공식 루머 무시
3. 스팸성 계정, 반복 게시물 무시
4. 같은 내용이 여러 신뢰 계정에서 언급될 때만 반영
5. 불확실하면 "X 데이터 불충분" 으로 반환
"""


def with_x_search_rules(prompt: str) -> str:
    """Prepend X noise-filtering rules to Grok prompts."""
    return f"{X_SEARCH_NOISE_RULES.strip()}\n\n{prompt.lstrip()}"


def _x_search_calls(response: Any) -> int:
    return int(_tool_usage_details(response).get("x_search_calls", 0) or 0)


def _web_search_calls(response: Any) -> int:
    return int(_tool_usage_details(response).get("web_search_calls", 0) or 0)


def grok_with_web_and_x_search(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
    max_output_tokens: int = 1200,
    model: str | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Grok with web_search + x_search (최신 뉴스·X 반응)."""
    if not config.GROK_API_KEY:
        return None, {
            "mode": "disabled",
            "web_search_enabled": False,
            "x_search_enabled": False,
            "model": model or config.GROK_MODEL,
        }

    model_name = model or config.GROK_MODEL
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.GROK_API_KEY, base_url=config.GROK_BASE_URL)
        response = client.responses.create(
            model=model_name,
            input=[{"role": "user", "content": prompt}],
            tools=GROK_WEB_X_SEARCH_TOOLS,
            max_output_tokens=max_output_tokens,
        )
        text = (getattr(response, "output_text", None) or "").strip()
        web_calls = _web_search_calls(response)
        x_calls = _x_search_calls(response)
        meta: dict[str, Any] = {
            "mode": "grok+web+x_search",
            "model": model_name,
            "web_search_enabled": True,
            "x_search_enabled": True,
            "web_search_calls": web_calls,
            "x_search_calls": x_calls,
            "web_search_used": web_calls > 0,
            "x_search_used": x_calls > 0,
        }
        if logger and getattr(response, "usage", None):
            usage = response.usage
            logger.log(
                model_name,
                agent,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            )
        return text or None, meta
    except Exception as exc:
        return None, {
            "mode": "error",
            "model": model_name,
            "web_search_enabled": False,
            "x_search_enabled": False,
            "error": str(exc),
        }


def grok_with_x_search(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
    max_output_tokens: int = 1200,
    model: str | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Call Grok vote model (GROK_VOTE_MODEL) with x_search for real-time X data."""
    if not config.GROK_API_KEY:
        return None, {"mode": "disabled", "x_search_enabled": False, "model": model or config.GROK_MODEL}

    model_name = model or config.GROK_MODEL
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.GROK_API_KEY, base_url=config.GROK_BASE_URL)
        response = client.responses.create(
            model=model_name,
            input=[{"role": "user", "content": prompt}],
            tools=GROK_X_SEARCH_TOOL,
            max_output_tokens=max_output_tokens,
        )
        text = (getattr(response, "output_text", None) or "").strip()
        meta: dict[str, Any] = {
            "mode": "grok+x_search",
            "model": model_name,
            "x_search_enabled": True,
            "x_search_calls": _x_search_calls(response),
        }

        if logger and getattr(response, "usage", None):
            usage = response.usage
            logger.log(
                model_name,
                agent,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            )

        return text or None, meta
    except Exception as exc:
        return None, {
            "mode": "error",
            "model": model_name,
            "x_search_enabled": False,
            "error": str(exc),
        }


def grok_x_search_json(
    prompt: str,
    *,
    agent: str,
    logger: Any = None,
    max_output_tokens: int = 2000,
    model: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Call Grok with X search and parse JSON from the response."""
    text, meta = grok_with_x_search(
        with_x_search_rules(prompt),
        agent=agent,
        logger=logger,
        max_output_tokens=max_output_tokens,
        model=model,
    )
    if not text:
        return None, meta
    parsed = safe_json_parse(text)
    if isinstance(parsed, dict):
        meta["parsed_ok"] = True
        return parsed, meta
    meta["parsed_ok"] = False
    meta["raw_text"] = text[:500]
    return None, meta
