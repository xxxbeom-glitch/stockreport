"""Shared helpers for sequential agent pipeline."""

from __future__ import annotations

from typing import Any

from config import VOLUME_BOLT, VOLUME_FIRE


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("%", "").strip()
        if not text or text.upper() in {"N/A", "NONE", "NULL", "-"}:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def fmt_pct(value: Any) -> str:
    num = safe_float(value, 0.0)
    return f"{num:+.2f}%"


def fmt_krw(value: Any) -> str:
    num = safe_float(value, 0.0)
    if num <= 0:
        return "N/A"
    return f"{int(round(num)):,}원"


def fmt_foreign_net_eok(value: Any) -> str:
    amount = safe_float(value, 0.0)
    if amount == 0:
        return "N/A"
    eok = int(amount / 100_000_000)
    sign = "+" if eok > 0 else ""
    return f"{sign}{abs(eok):,}억"


def volume_emoji(volume_ratio: float) -> str:
    if volume_ratio >= VOLUME_FIRE:
        return "🔥"
    if volume_ratio >= VOLUME_BOLT:
        return "⚡"
    return ""


def position_52w_pct(price: Any, low: Any, high: Any) -> float | None:
    p = safe_float(price, 0.0)
    lo = safe_float(low, 0.0)
    hi = safe_float(high, 0.0)
    if hi <= lo or p <= 0:
        return None
    return (p - lo) / (hi - lo) * 100


def position_52w_label(price: Any, low: Any, high: Any) -> str:
    pct = position_52w_pct(price, low, high)
    if pct is None:
        return "N/A"
    return f"{pct:.0f}%"


def distance_from_high_pct(price: Any, high: Any) -> float | None:
    p = safe_float(price, 0.0)
    hi = safe_float(high, 0.0)
    if hi <= 0 or p <= 0:
        return None
    return (p - hi) / hi * 100


def indicator_change_pct(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    change = str(row.get("change", ""))
    if change.upper() == "N/A":
        return None
    try:
        return float(change.replace("%", "").replace("+", "").strip())
    except ValueError:
        return None


def truncate_comment(text: Any, max_len: int = 40) -> str:
    """Legacy short clip (Slack one-liners, etc.)."""
    raw = " ".join(str(text or "").split())
    if not raw or raw.upper() in {"N/A", "NONE", "NULL"}:
        return ""
    for sep in (". ", "。", "!", "?", "\n"):
        if sep in raw:
            raw = raw.split(sep, 1)[0].strip()
            break
    if len(raw) > max_len:
        return raw[: max_len - 1].rstrip() + "…"
    return raw


def format_analyst_comment(text: Any, max_sentences: int = 3) -> str:
    """Up to N natural Korean sentences for HTML agent opinions."""
    import re

    raw = str(text or "").strip()
    if not raw or raw.upper() in {"N/A", "NONE", "NULL"}:
        return ""

    normalized = " ".join(raw.split())
    chunks = re.split(r"(?<=[.!?…])\s+|(?<=[。])\s*", normalized)
    sentences = [c.strip() for c in chunks if c.strip()]
    if not sentences:
        sentences = [normalized]

    picked: list[str] = []
    for sent in sentences:
        if len(picked) >= max_sentences:
            break
        picked.append(sent)

    return " ".join(picked)


ANALYST_VOICE_RULES = """
말투·형식 (반드시 준수):
- 숫자만 나열하지 말고, 그 숫자가 의미하는 바를 쉬운 말로 해석할 것
- 최대 3문장, 전문가가 옆에서 설명하듯 자연스러운 구어체 (~해요, ~예요, ~세요)
- 딱딱한 보고서체·명사 나열·JSON 설명 문구 금지
- comment(또는 risk_comment) 필드에만 본문을 쓸 것
"""


def volume_flow_label(volume_ratio: float, change_pct: float) -> str:
    """Classify volume surge as accumulation vs distribution."""
    if volume_ratio >= 2.0 and change_pct > 0.5:
        return "거래량↑·상승, 매집 우위"
    if volume_ratio >= 2.0 and change_pct < -0.5:
        return "거래량↑·하락, 차익실현 주의"
    if volume_ratio >= 1.5:
        return "거래량 증가, 추세 확인"
    return "거래량 보통"


def compute_stop_loss(price: Any, ratio: float = 0.94) -> str:
    p = safe_float(price, 0.0)
    if p <= 0:
        return "N/A"
    return fmt_krw(p * ratio)


def normalize_phase(phase: str) -> str:
    text = (phase or "").strip()
    if "위험회피" in text or "risk" in text.lower():
        return "위험회피"
    if "강세" in text or "위험선호" in text or "bull" in text.lower():
        return "강세"
    return "중립"
