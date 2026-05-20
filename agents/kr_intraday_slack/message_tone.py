"""슬랙 메시지 자연스러운 말투·길이 제한."""

from __future__ import annotations

import re
from typing import Any

# 딱딱한 표현 → 쉬운 말투
_SOFTEN_MAP: tuple[tuple[str, str], ...] = (
    ("X 데이터 불충분", "관련 이슈는 아직 뚜렷하진 않지만, 섹터 흐름은 확인할 만합니다"),
    ("x 데이터 불충분", "관련 이슈는 아직 뚜렷하진 않지만, 섹터 흐름은 확인할 만합니다"),
    ("데이터 불충분", "뚜렷한 새 소식은 아직 적어 보입니다"),
    ("섹터 증대", "쪽으로 다시 관심이 붙는"),
    ("거래대금이 활발", "거래가 다시 붙는"),
    ("거래대금 활발", "거래가 붙는"),
    ("으로 활발", "으로 거래가 붙는"),
    ("활발.", "거래가 붙는 흐름입니다."),
    ("활발,", "거래가 붙는 흐름이고,"),
    ("활발 ", "거래가 붙는 "),
    ("수급이 양호", "수급이 나아지는"),
    ("수급 양호", "수급이 괜찮은"),
    ("중립적이나", "크게 흔들리진 않지만"),
    ("중립,", "분위기는 애매하지만,"),
    ("중립 ", "분위기는 애매하지만 "),
    ("증가와", "늘면서"),
    ("증가", "늘면서"),
    ("부각됨", "눈에 띄고"),
    ("부각", "눈에 띄는"),
    ("지속", "이어지는"),
    ("확인되지 않음", "아직 잘 안 보입니다"),
    ("확인 어려움", "아직 잘 안 보입니다"),
    ("관망", "지켜보는"),
)

# 데이터 나열 패턴 제거(숫자 나열 문장 축소)
_DATA_NOISE = re.compile(
    r"(거래대금\s*[\d,]+\s*억|외국인\s*순매수\s*[\d,]+\s*억|기관\s*순매수\s*[\d,]+\s*억|"
    r"볼륨비\s*[\d.]+\s*배|52주\s*고점\s*대비\s*[\d.]+\s*%|장중\s*고가\s*[\d,]+|"
    r"현재\s*[\d,]+로\s*하락)[,.\s]*",
    re.IGNORECASE,
)

_STIFF_MARKERS = (
    "판단:",
    "진입 관점:",
    "주의 조건:",
    "시장·X 맥락",
    "섹터 증대",
    "데이터 불충분",
    "으로 활발",
    "수급이 양호",
)

_MAX_LINES = 11
_MAX_CHARS = 520


def soften_text(text: str) -> str:
    if not text:
        return ""
    out = text.strip()
    for old, new in _SOFTEN_MAP:
        out = out.replace(old, new)
    out = _DATA_NOISE.sub("", out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s*,\s*,", ",", out)
    return out.strip(" ,.")


def _usable_hint(text: str) -> str:
    """숫자 나열·깨진 조각을 제외한 짧은 맥락."""
    if not text:
        return ""
    t = soften_text(text)
    clause = re.split(r"[,，]\s*", t)[0].strip()
    if not clause or len(clause) < 10:
        return ""
    if re.search(r"\d", clause):
        return ""
    broken = ("으로 거래", "으로 붙", "분위기는 애매하지만", "확인할 만")
    if any(b in clause for b in broken):
        return ""
    if len(clause) > 56:
        clause = clause[:55].rstrip() + "…"
    return clause


def first_short_sentence(text: str, *, max_len: int = 72) -> str:
    """첫 문장만 짧게."""
    hint = _usable_hint(text)
    if hint:
        return hint
    t = soften_text(text)
    parts = re.split(r"(?<=[.!?])\s+|[\n]+", t)
    sentence = (parts[0] if parts else t).strip()
    if re.search(r"\d", sentence) or len(sentence) < 10:
        return ""
    if len(sentence) > max_len:
        sentence = sentence[: max_len - 1].rstrip() + "…"
    return sentence


def grok_one_liner(row: dict[str, Any]) -> str:
    """Grok 맥락 1줄 (이슈: 접두 optional)."""
    if row.get("grok_status") != "ok":
        return ""
    raw = (
        str(row.get("grok_why_now", "")).strip()
        or str(row.get("grok_mention_summary", "")).strip()
        or str(row.get("grok_sector_issue", "")).strip()
    )
    if not raw:
        return ""
    line = soften_text(raw)
    if "뚜렷한 새 소식" in line or "이슈는 아직" in line:
        return ""
    if len(line) > 70:
        line = line[:69].rstrip() + "…"
    if line.startswith("이슈:"):
        return line
    return f"이슈: {line}" if line else ""


def _pullback_line(entry_range: str) -> str:
    if entry_range and entry_range != "—":
        return (
            f"다만 바로 따라가기보다는, {entry_range} 구간까지 눌리는지 "
            "보는 게 좋아 보입니다."
        )
    return (
        "다만 바로 따라가기보다는, 예약가 후보 구간까지 눌리는지 "
        "보는 게 좋아 보입니다."
    )


def _watch_line(row: dict[str, Any]) -> str:
    sector = str(row.get("sector_name", "")).strip()
    hint = first_short_sentence(str(row.get("ai_reason", "")))
    grok = grok_one_liner(row)

    if sector:
        base = f"지금 이 종목은 {sector} 쪽에서 다시 관심이 붙는 흐름입니다."
    elif hint:
        base = f"지금 이 종목은 {hint}"
        if not base.endswith(("습니다", "입니다", "요", "다")):
            base += " 흐름입니다."
    else:
        base = "지금 이 종목은 장중에 다시 볼 만한 흐름입니다."

    if grok:
        return f"{base} {grok}"
    return base


def _cancel_line(row: dict[str, Any]) -> str:
    raw = soften_text(str(row.get("ai_cancel_condition", "")))
    if not raw:
        return "가격 이탈 또는 거래가 급격히 줄면 오늘은 넘기기"
    # 한 줄로 압축
    line = raw.replace("\n", " ").strip()
    price_m = re.search(r"([\d,]+)\s*원", line)
    price_plain = re.search(r"(\d{4,6})\s*이하", line)
    if price_m and ("이탈" in line or "이하" in line):
        return f"{price_m.group(1)}원 이탈 또는 거래 급감 시 오늘은 넘기기"
    if price_plain:
        p = f"{int(price_plain.group(1)):,}"
        return f"{p}원 이탈 또는 거래 급감 시 오늘은 넘기기"
    if "거래" in line and ("급" in line or "줄" in line):
        return line if len(line) <= 55 else "거래 급감·가격 이탈 시 오늘은 넘기기"
    if len(line) > 55:
        line = first_short_sentence(line, max_len=52)
    return line or "가격 이탈 또는 거래 급감 시 오늘은 넘기기"


def compose_slack_message(row: dict[str, Any]) -> str | None:
    """자연스러운 말투 슬랙 본문 (6~11줄)."""
    if not row.get("ai_send_slack"):
        return None

    status = str(row.get("ai_decision") or row.get("status") or "")
    name = str(row.get("name", ""))
    price = str(row.get("current_price_fmt") or row.get("current_price") or "N/A")
    entry_range = str(row.get("entry_range") or "—")
    entry_view = soften_text(str(row.get("ai_entry_view", "")))
    caution = str(row.get("ai_cancel_condition", "")).strip()

    if not status or not name or not caution:
        return None

    entry_hint = ""
    if entry_range and entry_range != "—":
        entry_hint = f"{entry_range} 구간"
    elif entry_view:
        entry_hint = "예약가 후보 구간"

    entry_sentence = "1주 테스트라면 이 구간에서만 진입을 검토하고,"
    if entry_hint:
        entry_sentence = f"1주 테스트라면 {entry_hint}에서만 진입을 검토하고,"

    lines = [
        f"[{status}] {name}",
        "",
        f"현재가: {price}",
        f"예약가 후보: {entry_range}",
        "",
        _watch_line(row),
        _pullback_line(entry_range),
        "",
        entry_sentence,
        "아래 취소 조건이 나오면 오늘은 넘기는 쪽이 안전합니다.",
        "",
        "취소 조건:",
        _cancel_line(row),
    ]

    text = "\n".join(lines)
    return _trim_message(text)


def _trim_message(text: str) -> str:
    """너무 길면 중복·빈 줄 축소."""
    if len(text) <= _MAX_CHARS and text.count("\n") + 1 <= _MAX_LINES:
        return text
    lines = text.split("\n")
    compact: list[str] = []
    for line in lines:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)
    while len("\n".join(compact)) > _MAX_CHARS and len(compact) > 8:
        # 중간 빈 줄 하나 제거
        try:
            idx = compact.index("")
            compact.pop(idx)
        except ValueError:
            break
    return "\n".join(compact)


def is_message_too_stiff(text: str) -> bool:
    lower = text.lower()
    return any(m in text or m.lower() in lower for m in _STIFF_MARKERS)


def is_message_too_long(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return len(lines) > 10 or len(text) > _MAX_CHARS


def has_required_slack_shape(text: str) -> bool:
    return "[" in text and "현재가" in text and "취소 조건" in text
