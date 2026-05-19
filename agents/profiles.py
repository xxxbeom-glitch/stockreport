"""Agent display profiles for report rendering."""

from __future__ import annotations

AGENT_PROFILES: list[dict[str, str]] = [
    {"key": "supply", "name": "James Park", "title": "수급 분석가", "emoji": "📊"},
    {"key": "momentum", "name": "Chris Yoon", "title": "모멘텀 트레이더", "emoji": "🚀"},
    {"key": "fundamental", "name": "이준혁", "title": "기업가치 분석가", "emoji": "📈"},
    {"key": "macro", "name": "Michael Chen", "title": "매크로 전략가", "emoji": "🌐"},
    {"key": "risk", "name": "강민서", "title": "리스크 매니저", "emoji": "🛡️"},
]

AGENT_BY_KEY: dict[str, dict[str, str]] = {p["key"]: p for p in AGENT_PROFILES}
