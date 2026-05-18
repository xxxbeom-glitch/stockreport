# AI 주식 에이전트 — 추가 모듈 가이드

> 기존 `STOCKREPORT_SETUP.md` + `STOCKREPORT_DATA.md` 에 이어서 작업
> 이 파일에서 다루는 것: 에이전트 5명 / 오케스트레이터 / PDF 생성 / HTML 템플릿 / GitHub Actions

---

## 목차

1. [에이전트 5명](#1-에이전트-5명)
2. [오케스트레이터 main.py](#2-오케스트레이터-mainpy)
3. [PDF 생성 모듈](#3-pdf-생성-모듈)
4. [HTML 템플릿](#4-html-템플릿)
5. [GitHub Actions 스케줄](#5-github-actions-스케줄)
6. [전체 실행 테스트](#6-전체-실행-테스트)

---

## 1. 에이전트 5명

### 역할 분담

```
Agent 1  수급 분석가      Grok 4.3       X 실시간 + 거래량 수급
Agent 2  모멘텀 트레이더  Grok 4.3       추세·52주 위치·과매수
Agent 3  펀더멘털 애널    Gemini 2.5 Pro PER·PBR·ROE·가이던스
Agent 4  매크로 전략가    Gemini 2.5 Pro 금리·환율·섹터 로테이션
Agent 5  리스크 매니저   Gemini 2.5 Pro 하방 리스크·손절 기준
```

---

### agents/supply_demand.py — 수급 분석가 (Grok)

```python
from openai import OpenAI
from config import GROK_API_KEY, GROK_BASE_URL, GROK_MODEL
import json

client = OpenAI(api_key=GROK_API_KEY, base_url=GROK_BASE_URL)

def analyze_supply_demand(market_data: dict) -> dict:
    """
    수급 분석가
    - 외국인·기관 순매수 흐름
    - 거래량 급등 종목 포착
    - X 실시간 수급 동향
    - 섹터 자금 유입·유출 방향
    """
    prompt = f"""
    너는 주식 수급 분석 전문가야.
    아래 데이터를 분석해서 수급 관점 투자 의견을 줘.
    초보 투자자도 이해할 수 있는 쉬운 말로.

    [시장 데이터]
    {json.dumps(market_data, ensure_ascii=False)[:3000]}

    분석 항목:
    1. 외국인·기관 순매수 상위 종목과 의미
    2. 거래량 급등 종목 — 왜 몰렸나 (평균 대비 배율 포함)
    3. 섹터별 자금 유입·유출 방향
    4. X(트위터)에서 화제인 수급 동향
    5. 수급 관점 매수·홀드·매도 의견

    JSON으로만 반환:
    {{
      "top_inflow_stocks": [
        {{"name": "종목명", "reason": "이유", "volume_x": "2.4배"}}
      ],
      "volume_alerts": [
        {{"name": "종목명", "volume_x": "3.1배", "change": "+4.2%", "is_up": true}}
      ],
      "sector_flow": {{
        "유입": ["섹터1", "섹터2"],
        "유출": ["섹터3"]
      }},
      "verdicts": {{
        "종목명": {{"vote": "매수", "reason": ["이유1", "이유2"]}}
      }},
      "summary": "한 줄 요약"
    }}
    """
    res = client.chat.completions.create(
        model=GROK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    return json.loads(res.choices[0].message.content)
```

---

### agents/momentum.py — 모멘텀 트레이더 (Grok)

```python
from openai import OpenAI
from config import GROK_API_KEY, GROK_BASE_URL, GROK_MODEL
import json

client = OpenAI(api_key=GROK_API_KEY, base_url=GROK_BASE_URL)

def analyze_momentum(market_data: dict) -> dict:
    """
    모멘텀 트레이더
    - 추세 방향과 강도
    - 52주 위치 분석
    - 단기 과매수 경고
    - 상승 모멘텀 지속 가능성
    """
    prompt = f"""
    너는 모멘텀 트레이딩 전문가야.
    아래 데이터를 분석해서 모멘텀 관점 의견을 줘.
    초보 투자자도 이해할 수 있는 쉬운 말로.

    [시장 데이터]
    {json.dumps(market_data, ensure_ascii=False)[:3000]}

    분석 항목:
    1. 각 종목 52주 위치 (고점 대비 %) — 90% 이상이면 고점 주의
    2. 현재 추세 방향과 강도
    3. 상승 모멘텀 지속 가능성
    4. 단기 과매수 구간 종목 경고
    5. 지금 가장 강한 테마·섹터

    JSON으로만 반환:
    {{
      "strong_momentum": [
        {{"name": "종목명", "position_52w": "76%", "trend": "강한 상승"}}
      ],
      "overbought_warning": [
        {{"name": "종목명", "position_52w": "94%", "reason": "고점 근접"}}
      ],
      "top_theme": "지금 가장 강한 테마",
      "verdicts": {{
        "종목명": {{"vote": "매수", "reason": ["이유1", "이유2"]}}
      }},
      "summary": "한 줄 요약"
    }}
    """
    res = client.chat.completions.create(
        model=GROK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    return json.loads(res.choices[0].message.content)
```

---

### agents/fundamental.py — 펀더멘털 애널 (Gemini)

```python
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_PRO
import json, re

genai.configure(api_key=GEMINI_API_KEY)

def analyze_fundamental(market_data: dict) -> dict:
    """
    펀더멘털 애널리스트
    - PER·PBR·ROE 밸류에이션
    - 실적 방향 (성장·정체·역성장)
    - 가이던스 신뢰도
    - 업종 평균 대비 평가
    """
    model  = genai.GenerativeModel(GEMINI_PRO)
    prompt = f"""
    너는 주식 펀더멘털 분석 전문가야.
    아래 데이터를 분석해서 펀더멘털 관점 투자 의견을 줘.
    초보 투자자도 이해할 수 있는 쉬운 말로.

    [시장 데이터]
    {json.dumps(market_data, ensure_ascii=False)[:3000]}

    분석 항목:
    1. PER — 업종 평균 대비 고평가·저평가 (숫자만 보지 말고 성장성 함께 판단)
    2. 영업이익률 — 100원 팔면 얼마 남는지
    3. 부채비율 — 빚이 많은지 적은지
    4. 실적 방향 (성장·정체·역성장)
    5. 가이던스 — 회사가 제시한 전망 신뢰도
    6. 목표주가 vs 현재가 (상승여력)

    JSON으로만 반환:
    {{
      "valuation": {{
        "종목명": {{
          "per": "32.4배",
          "per_vs_industry": "업종 평균 28배보다 높음",
          "verdict": "고평가지만 성장이 정당화"
        }}
      }},
      "earnings_trend": {{"종목명": "고성장"}},
      "guidance_quality": {{"종목명": "상향"}},
      "target_price": {{"종목명": {{"target": "210,000원", "upside": "+15%"}}}},
      "verdicts": {{
        "종목명": {{"vote": "매수", "reason": ["이유1", "이유2"]}}
      }},
      "summary": "한 줄 요약"
    }}
    JSON만 반환. 설명 없이.
    """
    res  = model.generate_content(prompt)
    text = re.sub(r'```json|```', '', res.text).strip()
    return json.loads(text)
```

---

### agents/macro.py — 매크로 전략가 (Gemini)

```python
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_PRO
import json, re

genai.configure(api_key=GEMINI_API_KEY)

def analyze_macro(indicators: dict, sector_temp: dict, news: str) -> dict:
    """
    매크로 전략가
    - 달러·금리·원자재 방향
    - 섹터 로테이션 판단
    - 시장 국면 진단
    - 지금 유리한 섹터
    """
    model  = genai.GenerativeModel(GEMINI_PRO)
    prompt = f"""
    너는 거시경제 및 주식 매크로 전략 전문가야.
    아래 데이터를 분석해서 매크로 관점 시장 전망을 줘.
    초보 투자자도 이해할 수 있는 쉬운 말로.

    [선행지표]
    {json.dumps(indicators, ensure_ascii=False)}

    [섹터 온도]
    {json.dumps(sector_temp, ensure_ascii=False)}

    [주요 뉴스]
    {news}

    분석 항목:
    1. 달러 방향 → 신흥국·원자재에 미치는 영향 (쉽게 설명)
    2. 금리 방향 → 성장주·가치주 중 유리한 쪽
    3. 원자재(유가·구리) → 경기 신호
    4. 지금 시장 국면 (위험선호/위험회피/중립)
    5. 섹터 로테이션 — 돈이 어디서 빠지고 어디로 가는지
    6. 지금 매크로 관점에서 유리한 섹터 TOP 3

    JSON으로만 반환:
    {{
      "market_phase": "위험선호",
      "market_phase_reason": "달러 약세 + 금리 안정 → 성장주 유리",
      "dollar_impact": "달러 약해지면 외국인 한국 주식 더 삼",
      "rate_impact": "금리 동결 → 성장주 부담 완화",
      "sector_rotation": {{
        "flowing_in": ["반도체", "방산"],
        "flowing_out": ["2차전지", "화학"]
      }},
      "favorable_sectors": ["AI반도체", "방산", "조선"],
      "unfavorable_sectors": ["2차전지", "소재"],
      "verdicts": {{
        "종목명": {{"vote": "매수", "reason": ["이유1", "이유2"]}}
      }},
      "summary": "한 줄 요약"
    }}
    JSON만 반환.
    """
    res  = model.generate_content(prompt)
    text = re.sub(r'```json|```', '', res.text).strip()
    return json.loads(text)
```

---

### agents/risk.py — 리스크 매니저 (Gemini)

```python
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_PRO
import json, re

genai.configure(api_key=GEMINI_API_KEY)

def analyze_risk(all_opinions: dict, market_data: dict) -> dict:
    """
    리스크 매니저
    - 다른 4명 의견 검토
    - 놓친 리스크 포착
    - 종목별 손절 기준
    - 포트폴리오 전체 리스크 수준
    """
    model  = genai.GenerativeModel(GEMINI_PRO)
    prompt = f"""
    너는 주식 리스크 관리 전문가야.
    4명 에이전트 의견을 검토하고 리스크 관점 최종 의견을 줘.
    초보 투자자도 이해할 수 있는 쉬운 말로.

    [4명 의견]
    {json.dumps(all_opinions, ensure_ascii=False)[:3000]}

    [시장 데이터]
    {json.dumps(market_data, ensure_ascii=False)[:1000]}

    분석 항목:
    1. 과매수 구간 종목 (52주 위치 90% 이상) — 주의 경고
    2. 다른 에이전트가 놓친 리스크
    3. 종목별 손절 기준 (몇 % 하락 시 재검토)
    4. 포트폴리오 전체 리스크 수준
    5. 지금 절대 하면 안 되는 것

    JSON으로만 반환:
    {{
      "overbought_warnings": [
        {{"name": "종목명", "position_52w": "91%", "warning": "고점 근접 — 추격 매수 주의"}}
      ],
      "hidden_risks": ["리스크1", "리스크2"],
      "stop_loss": {{"종목명": "-8% 이탈 시 재검토"}},
      "portfolio_risk": "보통",
      "do_not": "지금 절대 하면 안 되는 것",
      "verdicts": {{
        "종목명": {{"vote": "홀드", "reason": ["이유1", "이유2"]}}
      }},
      "summary": "한 줄 요약"
    }}
    JSON만 반환.
    """
    res  = model.generate_content(prompt)
    text = re.sub(r'```json|```', '', res.text).strip()
    return json.loads(text)
```

---

## 2. 오케스트레이터 main.py

```python
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_PRO
from data.us_market import (
    get_sector_temperature, get_us_indices,
    get_indicators, get_top_volume_stocks
)
from data.kr_market import (
    get_kr_indices, get_sector_flow_kr,
    get_foreign_flow, get_dynamic_targets,
    get_volume_leaders
)
from data.grok_realtime import (
    get_sector_buzz, get_premarket_movers, get_kr_market_buzz
)
from agents.supply_demand import analyze_supply_demand
from agents.momentum     import analyze_momentum
from agents.fundamental  import analyze_fundamental
from agents.macro        import analyze_macro
from agents.risk         import analyze_risk
from reports.pdf_generator import generate_pdf
from firebase_client     import save_report
from slack_sender        import send_report
import json, os, sys, re
from datetime import datetime

genai.configure(api_key=GEMINI_API_KEY)

def run_report(report_type: str):
    print(f"\n[{datetime.now().strftime('%H:%M')}] {report_type} 시작")

    # ── 1. 데이터 수집 ────────────────────────────────────
    print("  데이터 수집 중...")
    sector_temp_us = get_sector_temperature()
    sector_temp_kr = get_sector_flow_kr()
    indicators     = get_indicators()
    us_indices     = get_us_indices()
    kr_indices     = get_kr_indices()
    foreign_flow   = get_foreign_flow()
    kr_volume      = get_volume_leaders(market="KOSPI",  top=5)
    kd_volume      = get_volume_leaders(market="KOSDAQ", top=5)
    us_volume      = get_top_volume_stocks(
                       ["NVDA","AMD","MSFT","AAPL","TSLA","META","GOOGL"]
                     )
    dynamic_stocks = get_dynamic_targets()
    x_buzz         = get_sector_buzz()
    premarket      = get_premarket_movers()
    kr_buzz        = get_kr_market_buzz()

    market_data = {
        "report_type":    report_type,
        "date":           datetime.now().strftime("%Y년 %m월 %d일"),
        "us_indices":     us_indices,
        "kr_indices":     kr_indices,
        "sector_temp_us": sector_temp_us,
        "sector_temp_kr": sector_temp_kr,
        "indicators":     indicators,
        "foreign_flow":   foreign_flow,
        "kr_volume":      kr_volume,
        "kd_volume":      kd_volume,
        "us_volume":      us_volume,
        "dynamic_stocks": dynamic_stocks,
        "x_buzz":         x_buzz,
        "premarket":      premarket,
        "kr_buzz":        kr_buzz,
    }

    # ── 2. 에이전트 5명 분석 ─────────────────────────────
    print("  에이전트 분석 중...")
    supply   = analyze_supply_demand(market_data)
    momentum = analyze_momentum(market_data)
    fund     = analyze_fundamental(market_data)
    macro    = analyze_macro(
                   indicators,
                   {**sector_temp_us, **sector_temp_kr},
                   x_buzz + "\n" + kr_buzz
               )
    all_ops  = {
        "수급":     supply,
        "모멘텀":   momentum,
        "펀더멘털": fund,
        "매크로":   macro,
    }
    risk = analyze_risk(all_ops, market_data)

    # ── 3. Gemini Pro 오케스트레이터 — 5명 종합 ──────────
    print("  종합 분석 중...")
    model  = genai.GenerativeModel(GEMINI_PRO)
    prompt = f"""
    너는 주식 투자 전문가 팀의 팀장이야.
    5명 에이전트 분석을 종합해서 최종 리포트 데이터를 만들어.
    주식 1년차 초보 투자자가 읽는 리포트야.
    어려운 말 쓰지 말고 최대한 쉽게.

    [수급 분석가]
    {json.dumps(supply,    ensure_ascii=False)}

    [모멘텀 트레이더]
    {json.dumps(momentum,  ensure_ascii=False)}

    [펀더멘털 애널]
    {json.dumps(fund,      ensure_ascii=False)}

    [매크로 전략가]
    {json.dumps(macro,     ensure_ascii=False)}

    [리스크 매니저]
    {json.dumps(risk,      ensure_ascii=False)}

    [시장 데이터 요약]
    날짜: {market_data['date']}
    미국지수: {json.dumps(us_indices, ensure_ascii=False)}
    국내지수: {json.dumps(kr_indices, ensure_ascii=False)}
    섹터온도(미국): {json.dumps(dict(list(sector_temp_us.items())[:5]), ensure_ascii=False)}
    섹터온도(한국): {json.dumps(sector_temp_kr, ensure_ascii=False)}
    선행지표: {json.dumps(indicators, ensure_ascii=False)}

    최종 리포트 JSON으로만 반환:
    {{
      "report_type":      "{report_type}",
      "date":             "{market_data['date']}",
      "market_phase":     "오늘 시장 국면 한 줄",
      "one_line_summary": "오늘 핵심 한 줄 (쉽게)",
      "indices": {{
        "코스피":  {{"value": "2,754", "change": "+1.14%", "is_up": true}},
        "코스닥":  {{"value": "897",   "change": "+1.02%", "is_up": true}},
        "나스닥":  {{"value": "18,430","change": "+1.82%", "is_up": true}},
        "S&P500":  {{"value": "5,308", "change": "+0.94%", "is_up": true}}
      }},
      "indicators": {{
        "원달러":     {{"value": "1,334", "change": "-5원", "is_up": false}},
        "미국채10년": {{"value": "4.31%", "change": "보합",  "is_up": null}},
        "VIX":        {{"value": "14.2",  "change": "-1.8", "is_up": false}}
      }},
      "sector_flow": {{
        "hot":  ["섹터1", "섹터2"],
        "cold": ["섹터3", "섹터4"]
      }},
      "top_themes": [
        {{
          "name":    "테마명",
          "phase":   "초입",
          "desc":    "쉬운 설명 한 줄",
          "etf":     "TIGER 미국필라델피아반도체나스닥",
          "stocks":  ["종목1", "종목2"],
          "volume_leaders": [
            {{"name": "종목명", "ratio": "2.4배", "change": "+4.1%", "is_up": true}}
          ]
        }}
      ],
      "stock_analysis": [
        {{
          "name":       "종목명",
          "code":       "042700",
          "price":      "182,500원",
          "high_52":    "198,400원",
          "low_52":     "94,200원",
          "verdict":    "매수",
          "vote_count": "5명 중 4명 매수",
          "agent_votes": [
            {{"role": "수급",     "vote": "매수", "reason": ["이유1", "이유2"]}},
            {{"role": "모멘텀",   "vote": "매수", "reason": ["이유1", "이유2"]}},
            {{"role": "펀더멘털","vote": "매수", "reason": ["이유1", "이유2"]}},
            {{"role": "매크로",   "vote": "매수", "reason": ["이유1", "이유2"]}},
            {{"role": "리스크",   "vote": "홀드", "reason": ["이유1", "이유2"]}}
          ],
          "metrics": [
            {{"label": "PER",      "value": "32.4배", "sub": "업종 평균 28배"}},
            {{"label": "매출성장", "value": "+64%",   "sub": "전년 동기比"}},
            {{"label": "영업이익률","value": "38.2%", "sub": "분기 최고치"}},
            {{"label": "52주 위치","value": "91%",    "sub": "고점 근접 주의"}}
          ],
          "momentum_tags": [
            {{"text": "상승 모멘텀 강함", "heat": "hot"}},
            {{"text": "고점 부담",        "heat": "cold"}}
          ],
          "guidance": "2025년 연간 매출 1.2조 가이던스. 목표주가 210,000원."
        }}
      ],
      "action_items": ["액션1", "액션2", "액션3"],
      "risk_warning": "주의사항 한 줄",
      "glossary": [
        {{"term": "PER",    "definition": "주가가 순이익의 몇 배인지. 낮을수록 싸고 높을수록 비쌈"}},
        {{"term": "52주위치","definition": "최근 1년 최저~최고 범위에서 지금 주가 위치. 100%면 고점"}}
      ]
    }}
    """
    res         = model.generate_content(prompt)
    text        = re.sub(r'```json|```', '', res.text).strip()
    report_data = json.loads(text)

    # ── 4. PDF 생성 ───────────────────────────────────────
    print("  PDF 생성 중...")
    date_str = datetime.now().strftime("%y%m%d")
    filename = f"{date_str}_{report_type}.pdf"
    pdf_path = f"outputs/{filename}"
    os.makedirs("outputs", exist_ok=True)
    generate_pdf(report_data, pdf_path)

    # ── 5. Firebase 저장 ──────────────────────────────────
    print("  Firebase 저장 중...")
    pdf_url = save_report(report_data, pdf_path, filename)

    # ── 6. Slack 발송 ─────────────────────────────────────
    print("  Slack 발송 중...")
    send_report(pdf_url, report_data.get("one_line_summary", ""), report_type)

    print(f"  [{report_type}] 완료!")
    return pdf_url

if __name__ == "__main__":
    report_type = sys.argv[1] if len(sys.argv) > 1 else "kr_before"
    run_report(report_type)
```

---

## 3. PDF 생성 모듈

### reports/pdf_generator.py

```python
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
import os

TEMPLATE_MAP = {
    "us_after":  "01_us_after.html",
    "kr_before": "02_kr_before.html",
    "kr_during": "03_kr_during.html",
    "kr_after":  "04_kr_after.html",
    "us_before": "05_us_before.html",
    "weekly":    "06_weekly.html",
}

def generate_pdf(report_data: dict, output_path: str):
    env      = Environment(loader=FileSystemLoader("reports/templates"))
    tpl_name = TEMPLATE_MAP.get(
                   report_data.get("report_type", "kr_before"),
                   "02_kr_before.html"
               )
    template     = env.get_template(tpl_name)
    html_content = template.render(**report_data)

    HTML(
        string=html_content,
        base_url=os.path.abspath("reports/templates")
    ).write_pdf(output_path)

    print(f"  PDF 저장: {output_path}")
```

---

## 4. HTML 템플릿

### reports/templates/base.html — 공통 스타일

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');

* { box-sizing: border-box; margin: 0; padding: 0; }

@page {
  size: A4;
  margin: 0;
}

body {
  font-family: 'Noto Sans KR', sans-serif;
  font-size: 9pt;
  color: #1a1a1a;
  background: #f7f6f3;
  padding: 12mm 14mm 20mm;
}

/* ── 헤더 ──────────────────────────────────── */
.page-header {
  margin: -12mm -14mm 8mm;
  padding: 8mm 14mm;
  color: white;
}
.header-label {
  display: inline-block;
  background: white;
  font-size: 7.5pt;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 10px;
  margin-bottom: 4px;
}
.header-title { font-size: 13pt; font-weight: 700; }
.header-date  {
  font-size: 8pt;
  opacity: 0.75;
  float: right;
  margin-top: -20px;
}

/* ── 카드 ──────────────────────────────────── */
.card {
  background: white;
  border: 0.5px solid #e3e1da;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

/* ── 섹션 바 ───────────────────────────────── */
.section-bar {
  font-size: 8.5pt;
  font-weight: 700;
  padding: 4px 9px;
  border-radius: 4px;
  margin: 8px 0 6px;
}
.section-blue   { background: #e8f1fb; color: #1659a0; }
.section-green  { background: #e8f4df; color: #386a10; }
.section-amber  { background: #fdf2e0; color: #7d4b0a; }
.section-purple { background: #ecedfb; color: #4e47b0; }
.section-red    { background: #fceaea; color: #9e2b2b; }

/* ── 뱃지 ──────────────────────────────────── */
.badge {
  display: inline-block;
  font-size: 7pt;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
}
.badge-buy    { background: #e8f4df; color: #254d09; }
.badge-hold   { background: #fdf2e0; color: #5f3507; }
.badge-sell   { background: #fceaea; color: #751f1f; }
.badge-hot    { background: #e8f4df; color: #254d09; }
.badge-warm   { background: #fdf2e0; color: #5f3507; }
.badge-cold   { background: #fceaea; color: #751f1f; }
.badge-blue   { background: #e8f1fb; color: #0b4079; }
.badge-purple { background: #ecedfb; color: #38318a; }

/* ── 수치 색상 ─────────────────────────────── */
.up   { color: #236b1a; font-weight: 700; }
.down { color: #9e2b2b; font-weight: 700; }
.neut { color: #5a5956; }

/* ── 그리드 ────────────────────────────────── */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; }

/* ── 지수 카드 ─────────────────────────────── */
.index-card {
  background: white;
  border: 0.5px solid #e3e1da;
  border-radius: 6px;
  padding: 7px 10px;
}
.index-label { font-size: 7.5pt; color: #9c9a95; margin-bottom: 2px; }
.index-value { font-size: 11pt; font-weight: 700; }
.index-change { font-size: 7.5pt; }

/* ── 에이전트 투표 ─────────────────────────── */
.agent-votes {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 4px;
  margin: 6px 0;
}
.vote-chip {
  text-align: center;
  padding: 5px 3px;
  border-radius: 5px;
  border: 0.5px solid;
}
.vote-chip.buy  { background: #e8f4df; border-color: #7ec44a; }
.vote-chip.hold { background: #fdf2e0; border-color: #dfa020; }
.vote-chip.sell { background: #fceaea; border-color: #e07070; }
.vote-role      { font-size: 6.5pt; font-weight: 700; display: block; }
.vote-label     { font-size: 9pt;   font-weight: 700; display: block; }
.vote-reason    { font-size: 6pt;   color: #6b6b68; display: block; line-height: 1.3; }

/* ── 지표 박스 ─────────────────────────────── */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 5px;
  margin: 6px 0;
}
.metric-box   { background: #eeecea; border-radius: 4px; padding: 5px 7px; }
.metric-label { font-size: 7pt;   color: #9c9a95; }
.metric-value { font-size: 9.5pt; font-weight: 700; }
.metric-sub   { font-size: 6.5pt; color: #6b6b68; }

/* ── 모멘텀 태그 ───────────────────────────── */
.momentum-tags { display: flex; flex-wrap: wrap; gap: 4px; margin: 5px 0; }
.tag { font-size: 7pt; font-weight: 700; padding: 2px 8px; border-radius: 10px; border: 0.5px solid; }
.tag-hot  { background: #e8f4df; border-color: #7ec44a; color: #254d09; }
.tag-warm { background: #fdf2e0; border-color: #dfa020; color: #5f3507; }
.tag-cold { background: #fceaea; border-color: #e07070; color: #751f1f; }
.tag-neu  { background: #eeecea; border-color: #cbc9c2; color: #5a5956; }

/* ── 가이던스 ──────────────────────────────── */
.guidance {
  background: #e8f1fb;
  border-left: 2px solid #1659a0;
  padding: 5px 8px;
  border-radius: 0 4px 4px 0;
  font-size: 7.5pt;
  color: #636360;
  margin-top: 5px;
}
.guidance-label { font-size: 7.5pt; font-weight: 700; color: #1659a0; }

/* ── 거래량 테이블 ─────────────────────────── */
.volume-table { width: 100%; border-collapse: collapse; font-size: 8pt; }
.volume-table th {
  background: #eeecea;
  padding: 4px 8px;
  text-align: left;
  font-size: 7pt;
  color: #9c9a95;
  font-weight: 500;
}
.volume-table td { padding: 5px 8px; border-bottom: 0.5px solid #f1efe8; }
.volume-table tr:last-child td { border-bottom: none; }

/* ── 액션 박스 ─────────────────────────────── */
.action-box {
  border-radius: 6px;
  padding: 10px 12px;
  margin: 8px 0;
}
.action-box.green  { background: #e8f4df; }
.action-box.purple { background: #ecedfb; }
.action-title { font-size: 8.5pt; font-weight: 700; margin-bottom: 6px; }
.action-item  { font-size: 8pt; padding: 3px 0; display: flex; gap: 8px; }
.action-num   {
  background: white;
  border-radius: 50%;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 7pt;
  font-weight: 700;
  flex-shrink: 0;
}

/* ── 리스크 박스 ───────────────────────────── */
.risk-box {
  background: #fceaea;
  border-left: 2px solid #9e2b2b;
  padding: 6px 10px;
  border-radius: 0 4px 4px 0;
  margin: 6px 0;
}
.risk-label { font-size: 7.5pt; font-weight: 700; color: #9e2b2b; }
.risk-text  { font-size: 7.5pt; color: #1a1a1a; }

/* ── 꼬리말 용어 정리 ──────────────────────── */
.footer {
  position: fixed;
  bottom: 8mm;
  left: 14mm;
  right: 14mm;
}
.footer-line { border-top: 0.5px solid #e3e1da; margin-bottom: 5px; }
.glossary { background: #eeecea; border-radius: 4px; padding: 6px 10px; }
.glossary-row { font-size: 7.5pt; margin-bottom: 2px; }
.glossary-term { font-weight: 700; }
.glossary-def  { color: #636360; }
.page-note { font-size: 6.5pt; color: #9c9a95; text-align: center; margin-top: 4px; }
</style>
</head>
<body>
{% block content %}{% endblock %}
</body>
</html>
```

---

### reports/templates/02_kr_before.html — 국장 장전 (오전 8시)

```html
{% extends "base.html" %}
{% block content %}

<!-- 헤더 -->
<div class="page-header" style="background: #1b4f8a;">
  <span class="header-label" style="color: #1b4f8a;">국장 장전</span>
  <span class="header-date">{{ date }} 오전 8:00</span>
  <div class="header-title">오늘 장 열리기 전 필수 체크</div>
</div>

<!-- 오늘 국면 한 줄 -->
<div class="card" style="background: #e8f1fb; border-color: #1659a0;">
  <div style="font-size: 7.5pt; font-weight: 700; color: #1659a0; margin-bottom: 3px;">오늘 시장 국면</div>
  <div style="font-size: 9pt;">{{ market_phase }}</div>
</div>

<!-- 지수 -->
<div class="section-bar section-blue">어젯밤 미국 지수 + 오늘 선행지표</div>
<div class="grid-4" style="margin-bottom: 8px;">
  {% for name, idx in indices.items() %}
  <div class="index-card">
    <div class="index-label">{{ name }}</div>
    <div class="index-value {{ 'up' if idx.is_up else 'down' }}">{{ idx.value }}</div>
    <div class="index-change {{ 'up' if idx.is_up else 'down' }}">{{ idx.change }}</div>
  </div>
  {% endfor %}
</div>

<!-- 섹터 흐름 -->
<div class="section-bar section-green">섹터 자금 흐름 — 돈이 어디로 움직이나</div>
<div class="card">
  <div style="display: flex; gap: 20px;">
    <div>
      <div style="font-size: 7.5pt; font-weight: 700; color: #386a10; margin-bottom: 4px;">들어오는 곳 🔥</div>
      {% for s in sector_flow.hot %}
      <div class="badge badge-hot" style="margin: 2px;">{{ s }}</div>
      {% endfor %}
    </div>
    <div>
      <div style="font-size: 7.5pt; font-weight: 700; color: #9e2b2b; margin-bottom: 4px;">빠지는 곳 🔵</div>
      {% for s in sector_flow.cold %}
      <div class="badge badge-cold" style="margin: 2px;">{{ s }}</div>
      {% endfor %}
    </div>
  </div>
</div>

<!-- 주목 테마 -->
<div class="section-bar section-green">오늘 주목 테마</div>
{% for theme in top_themes %}
<div class="card">
  <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 5px;">
    <span style="font-size: 10pt; font-weight: 700;">{{ theme.name }}</span>
    <span class="badge badge-{{ 'hot' if theme.phase == '초입' else ('warm' if theme.phase == '진행중' else 'cold') }}">{{ theme.phase }}</span>
  </div>
  <div style="font-size: 8pt; color: #636360; margin-bottom: 6px;">{{ theme.desc }}</div>
  <div style="font-size: 7.5pt; margin-bottom: 3px;">
    <span style="font-weight: 700; color: #9c9a95;">ETF</span>
    <span style="color: #4e47b0; font-weight: 700; margin-left: 6px;">{{ theme.etf }}</span>
  </div>
  <div style="font-size: 7.5pt; margin-bottom: 6px;">
    <span style="font-weight: 700; color: #9c9a95;">종목</span>
    <span style="margin-left: 6px;">{{ theme.stocks | join(', ') }}</span>
  </div>
  <!-- 거래량 급등 -->
  {% if theme.volume_leaders %}
  <table class="volume-table">
    <tr>
      <th>거래량 급등 종목</th>
      <th>평균 대비</th>
      <th>등락</th>
    </tr>
    {% for s in theme.volume_leaders %}
    <tr>
      <td style="font-weight: 700;">{{ s.name }}</td>
      <td style="color: #7d4b0a; font-weight: 700;">{{ s.ratio }}</td>
      <td class="{{ 'up' if s.is_up else 'down' }}">{{ s.change }}</td>
    </tr>
    {% endfor %}
  </table>
  {% endif %}
</div>
{% endfor %}

<!-- 종목 심층 분석 -->
<div class="section-bar section-green">종목 심층 분석 — 에이전트 5명 의견</div>
{% for stock in stock_analysis %}
<div class="card">
  <!-- 종목 헤더 -->
  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 5px;">
    <div>
      <span style="font-size: 11pt; font-weight: 700;">{{ stock.name }}</span>
      <span style="font-size: 8pt; color: #9c9a95; margin-left: 5px;">{{ stock.code }}</span>
    </div>
    <div style="text-align: right;">
      <span class="badge badge-{{ 'buy' if stock.verdict == '매수' else ('hold' if stock.verdict == '홀드' else 'sell') }}" style="font-size: 8pt; padding: 3px 10px;">{{ stock.verdict }} 우세</span>
      <div style="font-size: 7pt; color: #9c9a95; margin-top: 2px;">{{ stock.vote_count }}</div>
    </div>
  </div>
  <div style="font-size: 7.5pt; color: #6b6b68; margin-bottom: 5px;">
    현재가 {{ stock.price }} &nbsp;|&nbsp; 52주 {{ stock.low_52 }} – {{ stock.high_52 }}
  </div>

  <!-- 에이전트 5명 투표 -->
  <div class="agent-votes">
    {% for ag in stock.agent_votes %}
    <div class="vote-chip {{ 'buy' if ag.vote == '매수' else ('hold' if ag.vote == '홀드' else 'sell') }}">
      <span class="vote-role">{{ ag.role }}</span>
      <span class="vote-label">{{ ag.vote }}</span>
      {% for r in ag.reason %}
      <span class="vote-reason">{{ r }}</span>
      {% endfor %}
    </div>
    {% endfor %}
  </div>

  <!-- 지표 4개 -->
  <div class="metric-grid">
    {% for m in stock.metrics %}
    <div class="metric-box">
      <div class="metric-label">{{ m.label }}</div>
      <div class="metric-value">{{ m.value }}</div>
      <div class="metric-sub">{{ m.sub }}</div>
    </div>
    {% endfor %}
  </div>

  <!-- 모멘텀 태그 -->
  <div class="momentum-tags">
    {% for tag in stock.momentum_tags %}
    <span class="tag tag-{{ tag.heat }}">{{ tag.text }}</span>
    {% endfor %}
  </div>

  <!-- 가이던스 -->
  <div class="guidance">
    <div class="guidance-label">가이던스 · 실적 전망</div>
    {{ stock.guidance }}
  </div>
</div>
{% endfor %}

<!-- 액션 아이템 -->
<div class="action-box green">
  <div class="action-title" style="color: #254d09;">오늘 할 것</div>
  {% for i, item in enumerate(action_items) %}
  <div class="action-item">
    <span class="action-num" style="color: #386a10;">{{ i+1 }}</span>
    <span>{{ item }}</span>
  </div>
  {% endfor %}
</div>

<!-- 꼬리말 -->
<div class="footer">
  <div class="footer-line"></div>
  {% if glossary %}
  <div class="glossary">
    <span style="font-size: 7.5pt; font-weight: 700; color: #6b6b68; margin-right: 8px;">용어 정리</span>
    {% for g in glossary %}
    <span class="glossary-row">
      <span class="glossary-term">{{ g.term }}</span>
      <span class="glossary-def"> — {{ g.definition }}&nbsp;&nbsp;</span>
    </span>
    {% endfor %}
  </div>
  {% endif %}
  <div class="page-note">투자 참고용입니다. 최종 판단은 본인이 직접 하세요.</div>
</div>

{% endblock %}
```

> **나머지 템플릿 (01, 03, 04, 05, 06) 은 02번을 기반으로 헤더 색상과 섹션 구성만 바꿔서 생성.**  
> Cursor에게 "02_kr_before.html 기반으로 나머지 5개 템플릿 만들어줘" 라고 하면 자동 생성.

---

## 5. GitHub Actions 스케줄

### cron 시간표 (UTC 기준)

| 리포트 | KST | UTC cron | 파일명 |
|--------|-----|----------|--------|
| 미장 장후 | 새벽 6시 | `0 21 * * 2-6` | 01_us_after.yml |
| 국장 장전 | 오전 8시 | `0 23 * * 1-5` | 02_kr_before.yml |
| 국장 장중 | 오후 12시 | `0 3 * * 2-6` | 03_kr_during.yml |
| 국장 장후 | 오후 4시 | `0 7 * * 2-6` | 04_kr_after.yml |
| 미장 장전 | 밤 11시 | `0 14 * * 1-5` | 05_us_before.yml |
| 위클리 | 토 오전 9시 | `0 0 * * 6` | 06_weekly.yml |

### .github/workflows/02_kr_before.yml

```yaml
name: 국장 장전 브리핑

on:
  schedule:
    - cron: '0 23 * * 1-5'
  workflow_dispatch:

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 패키지 설치
        run: |
          pip install -r requirements.txt
          sudo apt-get install -y fonts-nanum
          sudo apt-get install -y \
            libpango-1.0-0 libpangoft2-1.0-0 \
            libcairo2 libgdk-pixbuf2.0-0

      - name: 리포트 생성 및 발송
        env:
          GEMINI_API_KEY:           ${{ secrets.GEMINI_API_KEY }}
          GROK_API_KEY:             ${{ secrets.GROK_API_KEY }}
          SLACK_WEBHOOK_URL:        ${{ secrets.SLACK_WEBHOOK_URL }}
          FIREBASE_SERVICE_ACCOUNT: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          FIREBASE_STORAGE_BUCKET:  ${{ secrets.FIREBASE_STORAGE_BUCKET }}
        run: python main.py kr_before
```

> **나머지 5개 yml 파일은 위 파일에서 cron과 report_type만 바꿔서 생성.**

---

## 6. 전체 실행 테스트

### 단계별 테스트 순서

```powershell
cd D:\project\stockreport
venv\Scripts\activate

# 1. 데이터 수집 확인
python -c "
from data.us_market import get_sector_temperature
import json
result = get_sector_temperature()
for k, v in result.items():
    print(f'{k}: {v[\"temp\"]} ({v[\"ret_5d\"]}%)')
"

# 2. 한국 섹터 흐름 확인
python -c "
from data.kr_market import get_sector_flow_kr, get_dynamic_targets
import json
print(json.dumps(get_sector_flow_kr(), ensure_ascii=False, indent=2))
targets = get_dynamic_targets()
print(f'오늘 분석 대상: {len(targets)}개 종목')
"

# 3. Grok 실시간 데이터 확인
python -c "
from data.grok_realtime import get_sector_buzz
print(get_sector_buzz())
"

# 4. 에이전트 단독 테스트
python -c "
from agents.supply_demand import analyze_supply_demand
import json
result = analyze_supply_demand({'test': True, 'date': '2025-05-19'})
print(json.dumps(result, ensure_ascii=False, indent=2))
"

# 5. 전체 리포트 생성 (국장 장전)
python main.py kr_before

# outputs/ 폴더에서 PDF 확인
```

### 최종 체크리스트

```
□ 섹터 온도 데이터 정상 수집
□ 동적 종목 발굴 정상 작동
□ Grok API 응답 정상
□ Gemini API 응답 정상
□ JSON 파싱 오류 없음
□ PDF 생성 완료
□ Firebase 업로드 완료
□ Slack 수신 확인
□ GitHub Actions 수동 실행 (workflow_dispatch) 테스트
```

---

## 전체 파일 구조 최종본

```
D:\project\stockreport\
│
├── agents/
│   ├── __init__.py
│   ├── supply_demand.py   ← 이 파일
│   ├── momentum.py        ← 이 파일
│   ├── fundamental.py     ← 이 파일
│   ├── macro.py           ← 이 파일
│   └── risk.py            ← 이 파일
│
├── data/
│   ├── __init__.py
│   ├── us_market.py       ← STOCKREPORT_DATA.md
│   ├── kr_market.py       ← STOCKREPORT_DATA.md
│   └── grok_realtime.py   ← STOCKREPORT_DATA.md
│
├── reports/
│   ├── __init__.py
│   ├── pdf_generator.py   ← 이 파일
│   └── templates/
│       ├── base.html          ← 이 파일
│       ├── 01_us_after.html   ← base 기반 생성
│       ├── 02_kr_before.html  ← 이 파일
│       ├── 03_kr_during.html  ← base 기반 생성
│       ├── 04_kr_after.html   ← base 기반 생성
│       ├── 05_us_before.html  ← base 기반 생성
│       └── 06_weekly.html     ← base 기반 생성
│
├── .github/workflows/
│   ├── 01_us_after.yml    ← 이 파일 기반 생성
│   ├── 02_kr_before.yml   ← 이 파일
│   ├── 03_kr_during.yml   ← 이 파일 기반 생성
│   ├── 04_kr_after.yml    ← 이 파일 기반 생성
│   ├── 05_us_before.yml   ← 이 파일 기반 생성
│   └── 06_weekly.yml      ← 이 파일 기반 생성
│
├── main.py                ← 이 파일
├── config.py              ← STOCKREPORT_DATA.md
├── firebase_client.py     ← STOCKREPORT_SETUP.md
├── slack_sender.py        ← STOCKREPORT_SETUP.md
├── .env
├── .env.example
├── .gitignore
└── requirements.txt
```

---

*D:\project\stockreport — Agents + PDF + Actions v1.0*
