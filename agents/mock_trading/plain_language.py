# -*- coding: utf-8 -*-
"""추천 이유·위험 요인 → 초보자용 자연어(plainReason / plainRisk / viewGuide)."""

from __future__ import annotations

import re
from typing import Any

# 금지·치환: 긴 패턴을 먼저 적용
_PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"실적\s*컨센서스", "시장 기대 실적"),
    (r"어닝\s*서프라이즈", "실적이 기대보다 좋다는 소식"),
    (r"변동성\s*확대", "가격이 크게 흔들릴 수 있음"),
    (r"차익\s*실현", "이미 산 사람들이 팔아서 가격이 내려갈 수 있음"),
    (r"차익매물", "이미 산 사람들의 매도"),
    (r"리레이팅", "주가 평가가 다시 매겨지는 흐름"),
    (r"밸류에이션", "주가가 비싼지 싼지"),
    (r"오버행", "앞으로 많은 물량이 나올 가능성"),
    (r"모멘텀", "최근 오르는 흐름"),
    (r"수급", "사는·파는 사람 흐름"),
    (r"외국인\s*순매수", "외국인이 사고 있음"),
    (r"기관\s*순매수", "기관이 사고 있음"),
    (r"거래대금", "하루 거래 규모"),
    (r"유동성", "거래가 활발한 정도"),
    (r"HBM", "고속메모리(HBM)"),
    (r"CAPEX", "설비 투자"),
    (r"IR\b", "회사 설명회"),
    (r"OP\b", "영업이익"),
    (r"풀가동", "공장을 꽉 채워 가동"),
    (r"수퍼사이클", "업황이 오래 좋아지는 구간"),
)

_FORBIDDEN_ASSERTIONS = (
    "무조건",
    "반드시 매수",
    "확실한 수익",
    "확실히 오른",
    "무조건 상승",
)


def _clean_sentence(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    for pat, repl in _PHRASE_REPLACEMENTS:
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)
    s = re.sub(
        r"(\d+(?:\.\d+)?)\s*%\s*(?:급증|상승|증가)",
        r"\1% 정도 늘었다는 소식",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"최근\s*(\d+)\s*일\s*(?:간\s*)?(\d+(?:\.\d+)?)\s*%\s*상승",
        r"최근 \1일 동안 약 \2% 올랐어요",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"영업이익\s*(\d+(?:\.\d+)?)\s*%\s*급증",
        r"이익이 \1% 정도 크게 늘었다는 소식",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"손절[^\s,.]*", "", s, flags=re.IGNORECASE)
    for bad in _FORBIDDEN_ASSERTIONS:
        s = s.replace(bad, "")
    s = s.strip(" ,.;")
    s = re.sub(r"으로으로", "으로", s)
    s = re.sub(r"\s+으로\s+으로", "으로", s)
    if s and not re.search(r"[.!?]$", s):
        if re.search(r"(다|요|음|임|함)$", s):
            s += "."
        else:
            s += "요."
    s = s.replace("요요.", "요.").replace("..", ".")
    return s


def _rewrite_reason_line(line: str, name: str) -> str:
    raw = str(line or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    if any(k in raw for k in ("영업이익", "실적", "매출", "어닝")):
        return f"최근 실적·이익 쪽 좋은 소식이 나와 {name}에 관심이 붙고 있어요."
    if any(k in low for k in ("계약", "수주", "공급")):
        return f"새 계약·수주 소식이 나와 {name}에 기대감이 붙고 있어요."
    if "외국인" in raw:
        return "외국인 투자자가 사는 흐름이 이어지고 있어요."
    if re.search(r"\d+\s*%", raw) and any(k in raw for k in ("상승", "급증", "올랐", "상승")):
        return f"최근 주가가 꽤 올라 {name}을 눈여겨보는 사람이 많아요."
    if any(k in raw for k in ("거래", "거래대금", "거래량")):
        return "거래가 붙으면서 주목받는 흐름이에요."
    if any(k in low for k in ("ssd", "반도체", "hbm", "메모리")):
        return f"반도체·메모리 수요 관련 소식이 {name}에 우호적으로 작용하고 있어요."
    cleaned = _clean_sentence(raw)
    if len(cleaned) > 120:
        cleaned = cleaned[:117] + "..."
    return cleaned


def _rewrite_risk_line(line: str, name: str) -> str:
    raw = str(line or "").strip()
    if not raw:
        return ""
    if any(k in raw for k in ("급등", "차익", "급상승", "급격")):
        return (
            f"최근 {name} 주가가 빠르게 올라, 이미 기대가 반영됐을 수 있어요. "
            "추가 소식 없이 오르면 잠깐 팔려 나올 수도 있어요."
        )
    if any(k in raw for k in ("변동", "흔들", "저가")):
        return f"{name} 가격이 하루에 크게 흔들릴 수 있어요."
    if any(k in raw for k in ("섹터", "업황", "심리")):
        return "업종 전체 분위기가 꺾이면 함께 내려갈 수 있어요."
    cleaned = _clean_sentence(raw)
    if "급" in raw or "%" in raw:
        return f"최근 {name} 주가가 많이 올라, 잠시 숨 고르기가 나올 수 있어요."
    return cleaned


def _unique_lines(lines: list[str], *, limit: int = 3) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in lines:
        line = _clean_sentence(raw)
        if not line or len(line) < 8:
            continue
        key = re.sub(r"\W+", "", line.lower())[:48]
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= limit:
            break
    return out


def _join_sentences(
    lines: list[str],
    *,
    max_sentences: int = 2,
    rewriter=None,
    name: str = "",
) -> str:
    rewritten: list[str] = []
    for raw in lines:
        line = rewriter(raw, name) if rewriter else _clean_sentence(raw)
        line = (line or "").strip()
        if not line:
            continue
        key = re.sub(r"\W+", "", line.lower())[:48]
        if any(key in re.sub(r"\W+", "", x.lower()) for x in rewritten):
            continue
        rewritten.append(line)
        if len(rewritten) >= max_sentences:
            break
    return " ".join(rewritten).strip()


def _reason_templates(name: str, lines: list[str], grok: dict[str, Any] | None) -> list[str]:
    seeds = list(lines)
    g = grok or {}
    for sig in g.get("positive_signals") or []:
        seeds.append(str(sig))
    summary = str(g.get("summary") or "")
    if summary and "실적" in summary:
        seeds.append(f"{name} 실적·업황 관련 좋은 소식이 이어지고 있어요.")
    elif summary and len(summary) > 20:
        seeds.append(summary)
    return seeds


def _risk_templates(name: str, lines: list[str], grok: dict[str, Any] | None) -> list[str]:
    seeds = list(lines)
    g = grok or {}
    for sig in g.get("warning_signals") or []:
        seeds.append(str(sig))
    summary = str(g.get("summary") or "")
    if "VI" in summary or "급등" in summary:
        seeds.append("최근 주가가 빠르게 올라, 잠깐 크게 흔들릴 수 있어요.")
    return seeds


def _infer_plain_reason(name: str, reason_lines: list[str], grok: dict[str, Any] | None) -> str:
    seeds = _reason_templates(name, reason_lines, grok)
    text = _join_sentences(
        seeds, max_sentences=2, rewriter=_rewrite_reason_line, name=name
    )
    if text:
        return text
    return f"요즘 {name}에 사람들이 관심을 보이는 이유가 조금씩 쌓이고 있어요."


def _infer_plain_risk(name: str, risk_lines: list[str], grok: dict[str, Any] | None) -> str:
    seeds = _risk_templates(name, risk_lines, grok)
    text = _join_sentences(
        seeds, max_sentences=2, rewriter=_rewrite_risk_line, name=name
    )
    if text:
        return text
    return (
        f"{name} 주가는 좋은 소식만으로 계속 오르지 않을 수 있어요. "
        "추가 소식 없이 가격만 오르면 잠깐 내려갈 수도 있어요."
    )


def build_view_guide(plain_reason: str, plain_risk: str) -> str:
    """추천·위험을 종합한 관찰용 안내(매수 확정 아님)."""
    r = plain_reason.lower()
    k = plain_risk.lower()
    if any(w in k for w in ("급등", "빠르게 올", "차익", "흔들", "vi")):
        return (
            "관심 종목으로 보되, 장 초반에 급하게 오르면 바로 따라 사기보다 "
            "가격이 잠시 안정되는지 확인해보세요."
        )
    if any(w in r for w in ("실적", "이익", "매출", "계약", "수주", "공시")):
        return (
            "좋은 소식이 이어지는지 보면서, 주가가 이미 많이 반영됐는지도 "
            "함께 체크해보세요."
        )
    if any(w in r for w in ("외국인", "사는", "거래")):
        return (
            "사는 흐름은 참고하되, 뉴스 없이 가격만 오르면 잠시 지켜본 뒤 "
            "판단해보세요."
        )
    return (
        "관심 종목으로 두고, 하루 이틀 뉴스와 가격 흐름을 본 뒤 "
        "천천히 결정해보세요."
    )


def build_plain_copy(
    *,
    name: str,
    reason_lines: list[str],
    risk_lines: list[str],
    grok_validation: dict[str, Any] | None = None,
) -> dict[str, str]:
    grok = grok_validation if isinstance(grok_validation, dict) else None
    plain_reason = _infer_plain_reason(name, reason_lines, grok)
    plain_risk = _infer_plain_risk(name, risk_lines, grok)
    view_guide = build_view_guide(plain_reason, plain_risk)
    return {
        "plainReason": plain_reason,
        "plainRisk": plain_risk,
        "viewGuide": view_guide,
    }


def enrich_merged_card(
    card: dict[str, Any],
    *,
    extra_reasons: list[str] | None = None,
    extra_risks: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """merged_cards 항목에 plain 필드 추가(원문 필드 유지)."""
    out = dict(card)
    if (
        not force
        and out.get("plainReason")
        and out.get("plainRisk")
        and out.get("viewGuide")
    ):
        return out
    name = str(out.get("name") or "이 종목")
    reasons = list(out.get("reasons_sample") or [])
    if extra_reasons:
        reasons.extend(extra_reasons)
    risks: list[str] = []
    if extra_risks:
        risks.extend(extra_risks)

    plain = build_plain_copy(
        name=name,
        reason_lines=reasons,
        risk_lines=risks,
        grok_validation=out.get("grok_validation"),
    )
    out.update(plain)
    return out
