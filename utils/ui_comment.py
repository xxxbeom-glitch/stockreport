"""UI comment formatting (05_UI_COMMENT_RULES.md)."""

from __future__ import annotations

import re

_FORMAL_ENDINGS = re.compile(
    r"(습니다|입니다|합니다|됩니다|겠습니다|이에요|예요|해요)([.?!]?\s*)",
    re.MULTILINE,
)
_MULTI_SPACE = re.compile(r"[ \t]+")
_BUY_DIRECTIVE_PHRASES: tuple[str, ...] = (
    "매수하세요",
    "반드시 사야",
    "무조건 갑니다",
    "지금 안 사면 끝",
    "확실히 오릅니다",
    "꼭 사야",
    "지금 사야",
    "들어가세요",
    "진입하세요",
)


def to_memo_tone(text: str) -> str:
    """Drop formal speech; keep short memo-style phrasing."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    for phrase in _BUY_DIRECTIVE_PHRASES:
        raw = raw.replace(phrase, "")
    raw = _FORMAL_ENDINGS.sub(". ", raw)
    raw = raw.replace("..", ".").strip(" .")
    raw = _MULTI_SPACE.sub(" ", raw)
    return raw.strip()


def clamp_ui_comment_lines(text: str, *, max_lines: int = 2) -> str:
    """Keep at most max_lines non-empty lines."""
    memo = to_memo_tone(text)
    if not memo:
        return ""
    lines = [ln.strip() for ln in memo.replace("。", ".").split("\n") if ln.strip()]
    if not lines:
        return ""
    if len(lines) == 1 and len(lines[0]) > 96:
        parts = re.split(r"(?<=[.!?])\s+", lines[0])
        lines = [p.strip() for p in parts if p.strip()]
    return "\n".join(lines[:max_lines])


def format_ui_comment(text: str, *, max_lines: int = 2) -> str:
    """Full pipeline for template / Jinja output."""
    return clamp_ui_comment_lines(text, max_lines=max_lines)
