"""KR stock label constants (2-label MVP). See 09_KR_REPORT_FIX_RESULT.md."""

from __future__ import annotations

import re

# Final labels — exactly one of these two
LABEL_REGRET: str = "안 사면 후회함"
LABEL_TIMING: str = "지금 사기엔 좀..."

VALID_LABELS: tuple[str, ...] = (LABEL_REGRET, LABEL_TIMING)

# Higher = more bullish (for merge)
LABEL_BULLISHNESS: dict[str, int] = {
    LABEL_REGRET: 1,
    LABEL_TIMING: 0,
}

FORBIDDEN_PHRASES: tuple[str, ...] = (
    "매수하세요",
    "매수 하세요",
    "반드시 사야",
    "무조건 갑니다",
    "지금 안 사면 끝",
    "확실히 오릅니다",
    "꼭 사야",
    "지금 사야",
    "들어가세요",
    "진입하세요",
)

# Legacy 4-label / 매수홀드매도 → 2-label map
_LEGACY_VERDICT_MAP: dict[str, str] = {
    "매수": LABEL_REGRET,
    "홀드": LABEL_TIMING,
    "매도": LABEL_TIMING,
    "buy": LABEL_REGRET,
    "hold": LABEL_TIMING,
    "sell": LABEL_TIMING,
    "단기 주목": LABEL_REGRET,
    "관망": LABEL_TIMING,
}


def normalize_label(value: str | None, *, default: str = LABEL_TIMING) -> str:
    """Map arbitrary text to one of the two valid labels."""
    text = str(value or "").strip()
    if text in VALID_LABELS:
        return text
    if text in _LEGACY_VERDICT_MAP:
        return _LEGACY_VERDICT_MAP[text]
    lowered = text.lower()
    if "후회" in text or "regret" in lowered:
        return LABEL_REGRET
    if "좀" in text or "부담" in text or "과열" in text or "sell" in lowered:
        return LABEL_TIMING
    if "주목" in text or "관망" in text or "wait" in lowered or "hold" in lowered:
        return LABEL_TIMING
    if "매수" in text or "buy" in lowered:
        return LABEL_REGRET
    return default


def label_to_badge_class(label: str) -> str:
    """CSS badge class for report templates."""
    if label == LABEL_REGRET:
        return "buy"
    return "sell"


def sanitize_label_reason(text: str) -> str:
    """Strip buy-directive phrases; clamp to max 2 lines."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    for phrase in FORBIDDEN_PHRASES:
        raw = raw.replace(phrase, "")
    raw = re.sub(r"\s+", " ", raw).strip()

    lines = [ln.strip() for ln in raw.replace("。", ".").split("\n") if ln.strip()]
    if not lines:
        return ""
    if len(lines) == 1 and len(lines[0]) > 100:
        parts = re.split(r"(?<=[.!?])\s+", lines[0])
        lines = [p.strip() for p in parts if p.strip()]
    return "\n".join(lines[:2])


def reason_to_lines(reason: str) -> list[str]:
    """Split sanitized reason into at most 2 list items for templates."""
    text = sanitize_label_reason(reason)
    if not text:
        return []
    return [ln for ln in text.split("\n") if ln.strip()][:2]
