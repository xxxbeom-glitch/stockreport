"""슬랙 메시지 mrkdwn 포맷·자연스러운 말투."""

from __future__ import annotations

import re
from typing import Any

from data.kr_watchlist import watchlist_sector_labels

from .constants import SLACK_BODY_FORBIDDEN, SLACK_STOCK_SEPARATOR, slack_display_label

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
    "취소 조건",
    "시장·X 맥락",
    "섹터 증대",
    "데이터 불충분",
    "으로 활발",
    "수급이 양호",
)

_OBSERVE_DECISIONS = frozenset({"관찰 강화", "눌림 확인", "수급 반전 감지"})

_TITLE_EMOJI = "📌"
_LABEL_ENTRY_RANGE = "진입 후보 구간"
_ELLIPSIS_RE = re.compile(r"\.{3,}|…")
_MAX_LINES = 16
_MAX_CHARS = 900
_MAX_SUMMARY_LINES = 100
_MAX_SUMMARY_CHARS = 5500
_MAX_NARRATIVE_SENTENCES = 4
_MAX_ISSUE_SENTENCES = 2
_MAX_SENTENCE_CHARS = 140


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


def contains_slack_ellipsis(text: str) -> bool:
    """슬랙 본문에 줄임표(… / ...)가 있으면 True."""
    if not text:
        return False
    return bool(_ELLIPSIS_RE.search(text))


def _split_sentences(text: str) -> list[str]:
    t = soften_text(text.replace("\n", " "))
    if not t:
        return []
    parts = re.split(r"(?<=[.!?])\s+", t)
    out: list[str] = []
    for part in parts:
        p = part.strip()
        if not p or len(p) < 8 or contains_slack_ellipsis(p):
            continue
        if p[-1] not in ".!?":
            p = f"{p}."
        out.append(p)
    return out


def _complete_sentences(
    text: str,
    *,
    max_sentences: int = 2,
    max_chars: int = _MAX_SENTENCE_CHARS,
) -> list[str]:
    """완성 문장만 반환. 길면 자르지 않고 해당 문장은 생략."""
    chosen: list[str] = []
    for sentence in _split_sentences(text):
        if len(chosen) >= max_sentences:
            break
        if len(sentence) > max_chars:
            continue
        chosen.append(sentence)
    return chosen


def _reject_ellipsis_body(text: str) -> str:
    """줄임표로 끊긴 줄은 제거하거나, 완성 문장만 남김."""
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.rstrip()
        if not stripped:
            lines.append(line)
            continue
        if stripped.endswith("...") or stripped.endswith("…"):
            fixed = _ELLIPSIS_RE.sub("", stripped).strip()
            if len(fixed) >= 10 and fixed[-1] in ".!?":
                lines.append(fixed)
            continue
        if "..." in stripped or "…" in stripped:
            fixed = stripped.replace("…", "").replace("...", "").strip()
            if len(fixed) >= 10 and not contains_slack_ellipsis(fixed):
                lines.append(fixed)
            continue
        lines.append(line)
    return "\n".join(lines)


def sanitize_slack_mrkdwn(text: str) -> str:
    """Gemini 등 외부 출력 → 슬랙 본문 정규화."""
    if not text:
        return ""
    out = text.strip()
    out = re.sub(r"취소\s*조건\s*:", "• *경고*", out, flags=re.IGNORECASE)
    out = re.sub(r"아래\s*취소\s*조건", "아래 경고", out)
    out = out.replace("취소 조건", "경고")
    out = out.replace("예약가 후보", _LABEL_ENTRY_RANGE)
    out = re.sub(r"예약가\s*후보\s*:", f"*{_LABEL_ENTRY_RANGE}*", out)
    out = re.sub(r"(?<!\*)\b현재가\s*:", "*현재가*", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = _reject_ellipsis_body(out)
    return out.strip()


def join_intraday_slack_messages(messages: list[str]) -> str:
    """단일 섹터 요약 메시지 반환 (하위 호환)."""
    blocks = [sanitize_slack_mrkdwn(m) for m in messages if m and m.strip()]
    if not blocks:
        return ""
    return blocks[0]


def first_short_sentence(text: str, *, max_len: int = 140) -> str:
    """완성 문장 1개. 길면 생략(줄임표 금지)."""
    sentences = _complete_sentences(text, max_sentences=1, max_chars=max_len)
    return sentences[0] if sentences else ""


def _grok_raw_text(row: dict[str, Any]) -> str:
    if row.get("grok_status") != "ok":
        return ""
    return (
        str(row.get("grok_why_now", "")).strip()
        or str(row.get("grok_mention_summary", "")).strip()
        or str(row.get("grok_sector_issue", "")).strip()
    )


def grok_issue_sentences(row: dict[str, Any]) -> list[str]:
    """Grok 이슈 — 완성 문장 최대 2개, 줄임표·'이슈:' 접두 금지."""
    raw = _grok_raw_text(row)
    if not raw:
        return []
    line = soften_text(raw)
    if "뚜렷한 새 소식" in line or "이슈는 아직" in line:
        return []
    line = re.sub(r"^이슈\s*:\s*", "", line).strip()
    return _complete_sentences(line, max_sentences=_MAX_ISSUE_SENTENCES)


def grok_one_liner(row: dict[str, Any]) -> str:
    """하위 호환 — 첫 이슈 문장만."""
    sents = grok_issue_sentences(row)
    return sents[0] if sents else ""


def _has_entry_range(entry_range: str) -> bool:
    er = (entry_range or "").strip()
    return bool(er) and er not in ("—", "-", "N/A")


def _entry_range_display(entry_range: str) -> str:
    return entry_range.strip() if _has_entry_range(entry_range) else "-"


def _pullback_line(entry_range: str, decision: str) -> str:
    if _has_entry_range(entry_range):
        return (
            "다만 바로 따라가기보다는, 위 구간까지 눌리는지 "
            "보는 게 좋아 보입니다."
        )
    if decision in _OBSERVE_DECISIONS:
        return (
            "당장 따라가기보다 눌림·흐름이 이어지는지 "
            "지켜보는 편이 좋아 보입니다."
        )
    return "다만 바로 따라가기보다 눌림 구간을 먼저 확인하는 편이 좋아 보입니다."


def _watch_line(row: dict[str, Any], *, include_grok: bool = True) -> str:
    sector = str(row.get("sector_name", "")).strip()
    hint = first_short_sentence(str(row.get("ai_reason", "")))
    grok = grok_one_liner(row) if include_grok else ""

    if sector:
        base = f"{sector} 쪽에서 다시 관심이 붙는 흐름입니다."
    elif hint:
        base = hint
        if not base.endswith(("습니다", "입니다", "요", "다", "입니다.")):
            base += " 흐름입니다."
    else:
        base = "장중에 다시 볼 만한 흐름입니다."

    if grok:
        return f"{base}\n{grok}"
    return base


def _warning_line(row: dict[str, Any]) -> str:
    """매수가가 아닌 회피·무효 기준 (진입 후보 구간 무효 조건)."""
    raw = soften_text(str(row.get("ai_cancel_condition", "")))
    if not raw:
        return "가격 이탈 또는 거래 급감 시 오늘은 넘기기"
    line = raw.replace("\n", " ").strip()
    line = re.sub(r"취소\s*조건", "", line).strip(" :")
    line = re.sub(r"^(매수|진입)\s*(가|가격)\s*", "", line).strip()
    price_m = re.search(r"([\d,]+)\s*원", line)
    price_plain = re.search(r"(\d{4,6})\s*이하", line)
    if price_m and ("이탈" in line or "이하" in line):
        return f"{price_m.group(1)}원 이탈 또는 거래 급감 시 오늘은 넘기기"
    if price_plain:
        p = f"{int(price_plain.group(1)):,}"
        return f"{p}원 이탈 또는 거래 급감 시 오늘은 넘기기"
    if "거래" in line and ("급" in line or "줄" in line):
        complete = first_short_sentence(line, max_len=90)
        if complete:
            return complete
        return "거래 급감·가격 이탈 시 오늘은 넘기기"
    complete = first_short_sentence(line, max_len=90)
    return complete or "가격 이탈 또는 거래 급감 시 오늘은 넘기기"


def _one_share_line(entry_range: str, decision: str) -> str:
    """• *1주 기준* 아래 한 줄."""
    if _has_entry_range(entry_range):
        return f"{entry_range} 구간에서만 진입 검토"
    if decision in _OBSERVE_DECISIONS:
        return "눌림·흐름만 가볍게 확인"
    return "진입 후보 구간이 잡히기 전까지는 관찰 위주"


def _pullback_sentence(entry_range: str, decision: str) -> str:
    if _has_entry_range(entry_range):
        return _pullback_line(entry_range, decision)
    if decision in _OBSERVE_DECISIONS:
        return (
            "진입 후보 구간이 없으므로 지금은 눌림·흐름 확인 중심으로 "
            "보는 게 좋아 보입니다."
        )
    return (
        "진입 후보 구간이 없으므로 지금은 눌림 확인 중심으로 "
        "보는 게 좋아 보입니다."
    )


def _narrative_lines(
    row: dict[str, Any],
    entry_range: str,
    decision: str,
) -> list[str]:
    """종목 설명 2~4문장 (완성 문장만)."""
    sector = str(row.get("sector_name", "")).strip()
    lines: list[str] = []

    reason_sents = _complete_sentences(
        str(row.get("ai_reason", "")),
        max_sentences=1,
        max_chars=_MAX_SENTENCE_CHARS,
    )
    if reason_sents:
        lines.extend(reason_sents)
    elif sector:
        lines.append(f"{sector} 쪽에서 다시 관심이 붙는 흐름입니다.")
    else:
        lines.append("장중에 다시 볼 만한 흐름입니다.")

    for sent in grok_issue_sentences(row):
        if sent not in lines:
            lines.append(sent)

    pullback = _pullback_sentence(entry_range, decision)
    if pullback not in lines:
        lines.append(pullback)

    return lines[:_MAX_NARRATIVE_SENTENCES]


def compose_sector_stock_block(row: dict[str, Any]) -> str | None:
    """섹터 요약 안의 종목 카드 1건."""
    name = str(row.get("name", "")).strip()
    if not name or not str(row.get("ai_cancel_condition", "")).strip():
        return None

    price = str(row.get("current_price_fmt") or row.get("current_price") or "N/A")
    entry_raw = str(row.get("entry_range") or "")
    entry_display = _entry_range_display(entry_raw)
    decision = slack_display_label(str(row.get("ai_decision") or row.get("status") or ""))

    lines = [
        f"{_TITLE_EMOJI} *{name}*",
        "",
        f"*현재가* {price}",
        f"*{_LABEL_ENTRY_RANGE}* {entry_display}",
        "",
    ]
    lines.extend(_narrative_lines(row, entry_raw, decision))
    lines.extend(
        [
            "",
            "• *1주 기준*",
            _one_share_line(entry_raw, decision),
            "",
            "• *경고*",
            _warning_line(row),
        ]
    )
    return sanitize_slack_mrkdwn("\n".join(lines))


def group_rows_by_sector(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """sector_name 기준 그룹 (SendFilter 통과 종목만 넣을 것)."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sector = str(row.get("sector_name") or "").strip() or "기타"
        grouped.setdefault(sector, []).append(row)
    return grouped


def compose_sector_summary_message(
    *,
    slot_clock: str,
    scanned: int,
    send_rows: list[dict[str, Any]],
) -> str | None:
    """
    5개 관심 섹터 요약 1건.

    send_rows: SendFilter 통과 종목만 (전체 max_messages, 섹터당 최대 2, 1개 고정 아님).
    해당 섹터에 종목이 없으면 「진입 검토 종목 없음」.
    """
    if not send_rows:
        return None

    sector_labels = watchlist_sector_labels()
    grouped = group_rows_by_sector(send_rows)

    parts: list[str] = [
        "📊 *장중 관심종목 스캔*",
        "",
        f"기준 슬롯: {slot_clock}",
        f"스캔 대상: 관심종목 {scanned}개",
        "",
        SLACK_STOCK_SEPARATOR,
    ]

    for idx, sector in enumerate(sector_labels):
        rows = grouped.get(sector, [])
        parts.extend(["", f"*{sector}*"])
        if not rows:
            parts.append("진입 검토 종목 없음")
        else:
            parts.append(f"진입 검토 종목 {len(rows)}개")
            for row in rows:
                block = compose_sector_stock_block(row)
                if block:
                    parts.extend(["", block])

        if idx < len(sector_labels) - 1:
            parts.extend(["", SLACK_STOCK_SEPARATOR])

    text = sanitize_slack_mrkdwn("\n".join(parts))
    return _trim_summary(text)


def _trim_summary(text: str) -> str:
    if len(text) <= _MAX_SUMMARY_CHARS and text.count("\n") + 1 <= _MAX_SUMMARY_LINES:
        return text
    lines = text.split("\n")
    while len("\n".join(lines)) > _MAX_SUMMARY_CHARS and len(lines) > 20:
        # Grok '이슈:' 줄부터 제거 시도
        removed = False
        for i, ln in enumerate(lines):
            if ln.strip().startswith("이슈:"):
                lines.pop(i)
                removed = True
                break
        if not removed:
            lines.pop(len(lines) // 2)
    return "\n".join(lines)


def has_sector_summary_shape(text: str) -> bool:
    t = sanitize_slack_mrkdwn(text)
    if "장중 관심종목 스캔" not in t:
        return False
    if "기준 슬롯:" not in t:
        return False
    labels = watchlist_sector_labels()
    return all(label in t for label in labels)


def is_sector_summary_too_long(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return len(lines) > _MAX_SUMMARY_LINES or len(text) > _MAX_SUMMARY_CHARS


def _one_share_basis_detail(entry_range: str, decision: str, entry_view: str) -> str:
    if _has_entry_range(entry_range):
        return f"{entry_range} 구간에서만 진입 검토"
    view = soften_text(entry_view)
    if view and len(view) <= 60 and "테스트" not in view:
        return view
    if decision in _OBSERVE_DECISIONS:
        return "소액 기준으로 눌림·흐름만 가볍게 확인"
    return "진입 후보 구간이 잡히기 전까지는 관찰 위주로 보기"


def compose_slack_message(row: dict[str, Any]) -> str | None:
    """종목 카드 1건 (섹터 요약·Gemini fallback용)."""
    if not row.get("ai_send_slack"):
        return None
    return compose_sector_stock_block(row)


def _trim_message(text: str) -> str:
    if len(text) <= _MAX_CHARS and text.count("\n") + 1 <= _MAX_LINES:
        return text
    lines = text.split("\n")
    compact: list[str] = []
    for line in lines:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)
    while len("\n".join(compact)) > _MAX_CHARS and len(compact) > 9:
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
    return len(lines) > _MAX_LINES or len(text) > _MAX_CHARS


def has_required_slack_shape(text: str) -> bool:
    """종목 카드 형식."""
    t = sanitize_slack_mrkdwn(text)
    return (
        _TITLE_EMOJI in t
        and "*현재가*" in t
        and f"*{_LABEL_ENTRY_RANGE}*" in t
        and "• *경고*" in t
        and "• *1주 기준*" in t
    )


def contains_slack_body_forbidden(text: str) -> bool:
    lower = text.lower()
    return any(p in text or p in lower for p in SLACK_BODY_FORBIDDEN)
