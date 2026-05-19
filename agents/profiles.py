"""Agent display profiles for report rendering."""

from __future__ import annotations

AGENT_PROFILES: list[dict[str, str]] = [
    {"key": "macro", "name": "Michael Chen", "title": "매크로 애널리스트", "emoji": "🌐"},
    {"key": "supply", "name": "James Park", "title": "수급 애널리스트", "emoji": "📊"},
    {"key": "momentum", "name": "Chris Yoon", "title": "퀀트 애널리스트", "emoji": "🚀"},
    {"key": "fundamental", "name": "이준혁", "title": "기업 애널리스트", "emoji": "📈"},
    {"key": "risk", "name": "강민서", "title": "리스크 매니저", "emoji": "🛡️"},
]

AGENT_BY_KEY: dict[str, dict[str, str]] = {p["key"]: p for p in AGENT_PROFILES}
