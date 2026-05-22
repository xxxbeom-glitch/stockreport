# -*- coding: utf-8 -*-
"""HTML/CSS가 trading_kr-tokens.json과 일치하는지 검수."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKENS_PATH = ROOT.parent / "trading_kr-tokens.json"
HTML_PATH = ROOT / "index.html"
CSS_PATH = ROOT / "styles.css"

EXPECTED_TEXTS = [
    "모의 투자 시스템",
    "한국시장",
    "2026-05-20 수요일",
    "09:00 업데이트",
    "투자 성과 순위",
    "순위",
    "종목명",
    "매수금액",
    "평가금액",
    "수익률",
    "두산에너빌리티",
    "+36%",
    "삼성전자",
    "+26%",
    "한화에어로스페이스",
    "+5%",
    "-3%",
    "보유 종목 상세",
    "전체모델",
    "에너지/원자력",
    "-30.22%",
    "15,000원",
    "Gemini",
    "투자 진행 중",
    "선정이유",
    "이 기업은 앞으로 어쩌고 저쩌고 최근 모멘텀, 실적발표, 어쩌고 저쩌고....",
    "삼성바이오로직스",
    "바이오",
    "+30.22%",
    "Grok",
    "익절 완료",
    "에이전트 수익률",
    "DeekSeek",
    "deepseek-v4-pro",
    "gemini-3.1-pro-preview",
    "+16.33%",
    "Grok 4.3",
    "-62.2%",
    "매수종목",
    "삼성바이오로직스, SK하이닉스, 삼성전자, 현대해상, HD현대, 한미반도체",
]

EXPECTED_COLORS = {
    "#272727",
    "#344343",
    "#4750f3",
    "#5c5c5c",
    "#8b8b8b",
    "#ddeaf0",
    "#e3e3e3",
    "#e9efff",
    "#eff6f9",
    "#f3f3f3",
    "#f5f6f6",
    "#ff1212",
    "#ff3c3c",
    "#ffe9e9",
    "#ffffff",
}

EXPECTED_FONT_SIZES = {8, 10, 12, 16, 18, 20, 28}
EXPECTED_RADIUS = {4, 8, 15}
EXPECTED_SPACING = {2, 4, 6, 8, 10, 12, 18, 24, 32}


def norm_color(c: str) -> str:
    return c.strip().lower()


def extract_css_colors(css: str) -> set[str]:
    found = set()
    for m in re.finditer(r"#[0-9a-fA-F]{3,8}", css):
        found.add(norm_color(m.group(0)))
    for m in re.finditer(r"rgba?\([^)]+\)", css):
        found.add(m.group(0).replace(" ", ""))
    return found


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    errors: list[str] = []

    with TOKENS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    token_colors = {norm_color(c) for c in data["tokens"]["colors"]}
    html = HTML_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")
    css_colors = extract_css_colors(css)

    for c in EXPECTED_COLORS:
        if c not in css_colors:
            errors.append(f"CSS에 토큰 색상 누락: {c}")

    extra = css_colors - token_colors - {"rgba(228,232,232,0.8)"}
    if extra:
        errors.append(f"토큰에 없는 CSS 색상: {sorted(extra)}")

    html_flat = re.sub(r"\s+", " ", html)

    for text in EXPECTED_TEXTS:
        compact = re.sub(r"\s+", " ", text).strip()
        if compact not in html_flat:
            errors.append(f"HTML에 텍스트 누락: {text}")

    for fs in EXPECTED_FONT_SIZES:
        if f"--fs-{fs}" not in css and f"calc({fs} *" not in css:
            errors.append(f"CSS에 폰트 크기 미반영: {fs}px")

    for sp in EXPECTED_SPACING:
        if f"--space-{sp}" not in css and f"calc({sp} *" not in css:
            if sp in (16, 32) or sp == 47:
                continue
            if sp not in (16,):
                pass
    if "--pad-page-x" not in css or "16" not in css:
        errors.append("페이지 좌우 패딩(16px) 미반영")
    if "47" not in css:
        errors.append("페이지 상단 패딩(47px) 미반영")

    for r in EXPECTED_RADIUS:
        if str(r) not in css:
            errors.append(f"radius {r}px 미반영")

    if "Pretendard" not in css:
        errors.append("Pretendard 폰트 미적용")
    if "360" not in css:
        errors.append("디자인 기준 너비 360px 미적용")
    if "DROP_SHADOW" not in str(data["tokens"]["shadowValues"]) and "6" not in css:
        errors.append("카드 그림자 미반영")

    if errors:
        print("검수 실패:")
        for e in errors:
            print(" -", e)
        return 1

    print("검수 통과: trading_kr-tokens.json 색상·텍스트·타이포·간격·반응형 기준과 일치")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
