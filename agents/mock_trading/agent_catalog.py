# -*- coding: utf-8 -*-
"""UI·Firebase용 에이전트 카탈로그 (주차와 무관, 고정 4종)."""

from __future__ import annotations

from agents.mock_trading.models import AGENT_SPECS, AgentSpec

AGENT_DISPLAY_BY_KEY: dict[str, str] = {
    spec.agent_key: spec.display_name for spec in AGENT_SPECS
}

CANONICAL_AGENT_KEYS: tuple[str, ...] = tuple(spec.agent_key for spec in AGENT_SPECS)


def agent_display_name(agent_key: str) -> str:
    return AGENT_DISPLAY_BY_KEY.get(agent_key, agent_key)


def normalize_agent_keys(keys: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in keys or []:
        k = str(raw).strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def normalize_agent_names(names: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in names or []:
        n = str(raw).strip()
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def agent_keys_to_names(keys: list[str]) -> list[str]:
    return [agent_display_name(k) for k in keys]


def iter_canonical_specs() -> tuple[AgentSpec, ...]:
    return AGENT_SPECS
