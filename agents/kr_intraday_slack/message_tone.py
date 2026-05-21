"""슬랙 메시지 mrkdwn 포맷·자연스러운 말투."""

from __future__ import annotations

import re
from typing import Any

from data.kr_watchlist import watchlist_sector_labels

from .constants import (
    SLACK_BODY_FORBIDDEN,
    SLACK_STOCK_SEPARATOR,
    TIER_WAIT,
    TIER_WATCH_NOW,
    normalize_decision,
    slack_display_label,
)
from .entry_price import has_valid_entry_range

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
_LABEL_WATCH_ZONE = "볼 구간"
_MAX_STOCK_LINES = 5

_JARGON_SCRUB: tuple[tuple[str, str], ...] = (
    ("RS", "흐름"),
    ("모멘텀", "흐름"),
    ("저항", "올라가기 부담"),
    ("섹터 모멘텀", "업종 흐름"),
    ("관찰 구간", "볼 구간"),
    ("신규 후보", "새 후보"),
    ("진입 후보 구간", "볼 구간"),
    ("진입 검토", "지금 볼 만한 흐름"),
    ("추격", "따라가기"),
    ("수급", "거래"),
)

_OUTPUT_FORBIDDEN: tuple[str, ...] = (
    "추천",
    "진입하",
    "진입하세요",
    "진입 검토",
    "진입 후보",
    "신규 후보",
    "매수하세요",
    "매수 권",
    "무조건 매수",
)
_PROTECTED_PHRASES: tuple[str, ...] = ("외국인 매수",)
_ELLIPSIS_RE = re.compile(r"\.{3,}|…")
_MAX_LINES = 16
_MAX_CHARS = 900
_MAX_SUMMARY_LINES = 100
_MAX_SUMMARY_CHARS = 5500
_MAX_MAIN_SUMMARY_LINES = 7
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
    if _TITLE_EMOJI in out:
        out = re.sub(r"취소\s*조건\s*:", "• *경고*", out, flags=re.IGNORECASE)
        out = re.sub(r"아래\s*취소\s*조건", "아래 경고", out)
        out = out.replace("취소 조건", "경고")
        out = out.replace("예약가 후보", _LABEL_ENTRY_RANGE)
        out = re.sub(r"예약가\s*후보\s*:", f"*{_LABEL_ENTRY_RANGE}*", out)
        out = re.sub(r"(?<!\*)\b현재가\s*:", "*현재가*", out)
    else:
        out = out.replace("예약가 후보", _LABEL_WATCH_ZONE)
        out = out.replace(_LABEL_ENTRY_RANGE, _LABEL_WATCH_ZONE)
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
    return has_valid_entry_range(entry_range)


def _entry_range_display(entry_range: str) -> str:
    """유효한 구간만 표시. '-' 플레이스홀더 사용 안 함."""
    er = (entry_range or "").strip()
    return er if _has_entry_range(er) else ""


def scrub_easy_language(text: str) -> str:
    """슬랙 본문 — 쉬운 말투·금지 표현 정리."""
    out = soften_text(text)
    placeholders: dict[str, str] = {}
    for i, phrase in enumerate(_PROTECTED_PHRASES):
        if phrase in out:
            key = f"__PROT{i}__"
            placeholders[key] = phrase
            out = out.replace(phrase, key)
    for old, new in _JARGON_SCRUB:
        out = out.replace(old, new)
    for phrase in _OUTPUT_FORBIDDEN:
        out = out.replace(phrase, "")
    for key, phrase in placeholders.items():
        out = out.replace(key, phrase)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" ,.")


def tier_for_send_row(row: dict[str, Any]) -> str:
    """send_rows용 — green | yellow."""
    decision = normalize_decision(str(row.get("ai_decision") or row.get("status") or ""))
    if decision in TIER_WATCH_NOW:
        return "green"
    return "yellow"


def _format_watch_zone(row: dict[str, Any]) -> str:
    er = str(row.get("entry_range") or "").strip()
    if not has_valid_entry_range(
        er, entry_low=row.get("entry_low"), entry_high=row.get("entry_high")
    ):
        return ""
    m = re.match(r"([\d,]+)원\s*~\s*([\d,]+)원", er)
    if m:
        return f"{m.group(1)} ~ {m.group(2)}원"
    return er.replace("원 ~", " ~").replace("~ ", "~ ")


def _format_price_line(row: dict[str, Any]) -> str:
    price = str(row.get("current_price_fmt") or row.get("current_price") or "").strip()
    if not price or price in ("N/A", "0", "0원"):
        return ""
    if "원" not in price and price.replace(",", "").isdigit():
        return f"{price}원"
    return price


def _reason_text(row: dict[str, Any], *, extra: str = "") -> str:
    """이유 1~2문장 — 섹터명은 문장 안에만."""
    parts: list[str] = []
    raw_reason = str(row.get("ai_reason") or extra or "").strip()
    for sent in _complete_sentences(
        scrub_easy_language(raw_reason),
        max_sentences=2,
        max_chars=200,
    ):
        parts.append(sent)
    if len(parts) < 2:
        for sent in grok_issue_sentences(row):
            s = scrub_easy_language(sent)
            if s and s not in parts and len(s) <= 200:
                parts.append(s)
            if len(parts) >= 2:
                break
    if not parts:
        sector = str(row.get("sector_name") or "").strip()
        if sector:
            parts.append(f"{sector} 쪽 흐름을 오늘 다시 짚어볼 만합니다.")
        else:
            parts.append("장중에 다시 볼 만한 흐름입니다.")
    text = " ".join(parts[:2])
    return scrub_easy_language(text)


def _parse_won_value(value: Any) -> int:
    m = re.search(r"([\d,]+)", str(value or ""))
    if not m:
        return 0
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return 0


def _current_above_entry_high(row: dict[str, Any]) -> bool:
    current = _parse_won_value(
        row.get("current_price_fmt") or row.get("current_price")
    )
    try:
        high = int(row.get("entry_high") or 0)
    except (TypeError, ValueError):
        high = 0
    if high <= 0:
        er = str(row.get("entry_range") or "")
        m = re.search(r"~\s*([\d,]+)원", er)
        if m:
            high = _parse_won_value(m.group(1))
    return current > 0 and high > 0 and current > high


def _caution_text(row: dict[str, Any], *, pass_today: bool = False) -> str:
    if pass_today:
        return "무리하지 말고 다음 눌림이나 거래대금 회복을 보는 쪽이 낫습니다."
    if tier_for_send_row(row) == "yellow" and _current_above_entry_high(row):
        return "아래 구간으로 내려올 때 다시 확인하는 게 좋습니다."
    raw = scrub_easy_language(str(row.get("ai_cancel_condition") or ""))
    complete = first_short_sentence(raw, max_len=120)
    if complete and len(complete) >= 24:
        return complete
    entry_raw = str(row.get("entry_range") or "")
    if _has_entry_range(entry_raw):
        return "이미 많이 오른 상태라 바로 따라가기보다는 살짝 눌리는지 보는 게 좋습니다."
    return "가격 이탈이나 거래 급감이 나오면 오늘은 넘기는 편이 낫습니다."


def select_pass_today_rows(
    evaluated: list[dict[str, Any]],
    send_rows: list[dict[str, Any]],
    *,
    max_items: int = 3,
) -> list[dict[str, Any]]:
    """🔴 오늘은 패스 — 발송 제외·추격 등 (green/yellow 제외)."""
    from .send_filter import sort_rows_by_pick_score

    sent = {str(r.get("ticker") or "") for r in send_rows}
    pool: list[dict[str, Any]] = []
    for row in sort_rows_by_pick_score(evaluated):
        ticker = str(row.get("ticker") or "")
        if not ticker or ticker in sent:
            continue
        if row.get("is_chasing") or not row.get("ai_send_slack"):
            pool.append(row)
        if len(pool) >= max_items:
            break
    return pool


def compose_new_candidate_stock_block(
    row: dict[str, Any],
    *,
    pass_today: bool = False,
) -> str | None:
    """종목 1건 — 최대 5줄, 문장형 (볼 구간·이유·주의)."""
    name = str(row.get("name", "")).strip()
    if not name:
        return None

    lines: list[str] = [f"• {name}"]
    price = _format_price_line(row)
    if price:
        lines.append(f"현재가: {price}")

    zone = _format_watch_zone(row)
    if zone and not pass_today:
        lines.append(f"{_LABEL_WATCH_ZONE}: {zone}")

    reason = _reason_text(
        row,
        extra=str(row.get("ai_skip_reason") or "") if pass_today else "",
    )
    if reason:
        lines.append(f"이유: {reason}")

    caution = _caution_text(row, pass_today=pass_today)
    if caution:
        lines.append(f"주의: {caution}")

    if len(lines) < 2:
        return None
    return sanitize_slack_mrkdwn("\n".join(lines[:_MAX_STOCK_LINES]))


def compose_new_candidate_scan_message(
    *,
    slot_clock: str,
    send_rows: list[dict[str, Any]],
    pass_rows: list[dict[str, Any]] | None = None,
) -> str:
    """📡 오늘 새로 볼 종목 — 메인 슬랙 본문."""
    green_blocks: list[str] = []
    yellow_blocks: list[str] = []
    for row in send_rows:
        block = str(row.get("slack_stock_block") or "").strip()
        if not block:
            block = compose_new_candidate_stock_block(row) or ""
        if not block:
            continue
        if tier_for_send_row(row) == "green":
            green_blocks.append(block)
        else:
            yellow_blocks.append(block)

    red_blocks: list[str] = []
    for row in pass_rows or []:
        block = str(row.get("slack_stock_block") or "").strip()
        if not block:
            block = compose_new_candidate_stock_block(row, pass_today=True) or ""
        if block:
            red_blocks.append(block)

    total_new = len(green_blocks) + len(yellow_blocks)
    time_label = slot_clock.split()[-1] if " " in slot_clock else slot_clock

    lines = [
        "📡 오늘 새로 볼 종목",
        "",
        f"기준: {time_label}",
        f"새 후보: {total_new}개",
        "",
    ]

    def _append_section(title: str, blocks: list[str]) -> None:
        lines.append(title)
        lines.append("")
        if blocks:
            lines.extend(blocks)
            lines.append("")
        else:
            lines.append("_해당 없음_")
            lines.append("")

    _append_section("🟢 지금 볼만함", green_blocks)
    _append_section("🟡 조금 기다림", yellow_blocks)
    _append_section("🔴 오늘은 패스", red_blocks)

    return sanitize_slack_mrkdwn("\n".join(lines).strip())


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


def _default_warning_below_entry(entry_low: Any) -> str:
    try:
        lo = int(entry_low)
    except (TypeError, ValueError):
        return ""
    if lo <= 0:
        return ""
    warn = max(int(lo * 0.97), lo - 500)
    return f"{warn:,}원 이탈 또는 거래 급감 시 오늘은 넘기기"


def _warning_line(row: dict[str, Any]) -> str:
    """매수가가 아닌 회피·무효 기준 (진입 후보 구간보다 아래 이탈)."""
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
    if complete:
        return complete
    below = _default_warning_below_entry(row.get("entry_low"))
    if below:
        return below
    return "가격 이탈 또는 거래 급감 시 오늘은 넘기기"


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
    """섹터 요약 안의 종목 카드 1건. 진입 후보 구간 없으면 None."""
    name = str(row.get("name", "")).strip()
    if not name or not str(row.get("ai_cancel_condition", "")).strip():
        return None

    entry_raw = str(row.get("entry_range") or "")
    if not has_valid_entry_range(
        entry_raw, entry_low=row.get("entry_low"), entry_high=row.get("entry_high")
    ):
        return None

    price = str(row.get("current_price_fmt") or row.get("current_price") or "N/A")
    entry_display = _entry_range_display(entry_raw)
    if not entry_display:
        return None
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


def scan_header_timestamp(slot_clock: str) -> str:
    """KST 기준 `YYYY-MM-DD HH:MM` (슬롯 시각)."""
    from datetime import datetime, timedelta, timezone

    kst = datetime.now(timezone(timedelta(hours=9)))
    return f"{kst.strftime('%Y-%m-%d')} {slot_clock}"


def compose_main_scan_summary(
    *,
    slot_clock: str,
    send_rows: list[dict[str, Any]],
) -> str:
    """
    메인 채널용 짧은 요약 (5~7줄).
    SendFilter 통과 종목만 진입 후보로 나열.
    """
    labels = watchlist_sector_labels()
    grouped = group_rows_by_sector(send_rows)
    count = len(send_rows)

    lines = [
        f"📊 *{scan_header_timestamp(slot_clock)} 장중 관심종목 스캔*",
        "",
        f"*진입 후보:* {count}개",
    ]
    if count == 0:
        lines.append("오늘 슬롯 기준으로는 진입 검토할 종목이 없습니다.")
        text = sanitize_slack_mrkdwn("\n".join(lines))
        return _trim_main_summary(text)

    for sector in labels:
        for row in grouped.get(sector, []):
            name = str(row.get("name", "")).strip()
            if name:
                lines.append(f"- {sector}: {name}")

    text = sanitize_slack_mrkdwn("\n".join(lines))
    return _trim_main_summary(text)


def _trim_main_summary(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln is not None]
    while len(lines) > _MAX_MAIN_SUMMARY_LINES:
        if lines and lines[-1].startswith("- "):
            lines.pop()
        else:
            lines.pop()
    return "\n".join(lines)


def compose_sector_thread_message(
    sector: str,
    rows: list[dict[str, Any]],
) -> str:
    """섹터별 쓰레드 1건 — SendFilter 통과 종목 카드만."""
    lines = [f"*{sector}*"]
    if not rows:
        lines.append("진입 검토 종목 없음")
        return sanitize_slack_mrkdwn("\n".join(lines))

    lines.append(f"진입 검토 종목 {len(rows)}개")
    for row in rows:
        block = str(row.get("slack_stock_block") or "").strip()
        if not block:
            block = compose_sector_stock_block(row) or ""
        if block:
            lines.extend(["", block])

    return sanitize_slack_mrkdwn("\n".join(lines))


def has_main_scan_summary_shape(text: str) -> bool:
    t = sanitize_slack_mrkdwn(text)
    return "장중 관심종목 스캔" in t and "*진입 후보:*" in t


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
    """종목 블록 1건 (Gemini fallback·테스트)."""
    if row.get("ai_send_slack"):
        return compose_new_candidate_stock_block(row)
    return compose_new_candidate_stock_block(row, pass_today=True)


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


def has_new_candidate_stock_shape(text: str) -> bool:
    """📡 문장형 종목 블록 (최대 5줄)."""
    t = sanitize_slack_mrkdwn(text)
    if not t.startswith("• "):
        return False
    if "이유:" not in t or "주의:" not in t:
        return False
    if any(p in t for p in _OUTPUT_FORBIDDEN):
        return False
    if "진입" in t or "추천" in t:
        return False
    if "매수" in t and "외국인 매수" not in t:
        return False
    lines = [ln for ln in t.splitlines() if ln.strip()]
    return 2 <= len(lines) <= _MAX_STOCK_LINES


def has_new_candidate_scan_shape(text: str) -> bool:
    t = sanitize_slack_mrkdwn(text)
    return (
        "📡" in t
        and "오늘 새로 볼 종목" in t
        and "기준:" in t
        and "새 후보:" in t
        and "🟢 지금 볼만함" in t
        and "🟡 조금 기다림" in t
        and "🔴 오늘은 패스" in t
    )


def has_required_slack_shape(text: str) -> bool:
    """종목 블록 — 신규 문장형 우선, 레거시 카드 호환."""
    if has_new_candidate_stock_shape(text):
        return True
    t = sanitize_slack_mrkdwn(text)
    return (
        _TITLE_EMOJI in t
        and "*현재가*" in t
        and f"*{_LABEL_ENTRY_RANGE}*" in t
        and "• *경고*" in t
        and "• *1주 기준*" in t
    )


def is_new_candidate_stock_too_long(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return len(lines) > _MAX_STOCK_LINES or len(text) > 520


def contains_slack_body_forbidden(text: str) -> bool:
    lower = text.lower()
    return any(p in text or p in lower for p in SLACK_BODY_FORBIDDEN)
