# AI 주식 에이전트 — 보완 모듈 가이드

> 기존 3개 MD에 이어서 작업하는 마지막 파일  
> STOCKREPORT_SETUP + DATA + AGENTS 완료 후 이 파일 진행

---

## 목차

1. [스케줄 타이밍 조정](#1-스케줄-타이밍-조정)
2. [토큰 사용량 로깅](#2-토큰-사용량-로깅)
3. [유틸리티 모듈](#3-유틸리티-모듈)
4. [에러 핸들링 & 재시도](#4-에러-핸들링--재시도)
5. [주말·공휴일 처리](#5-주말공휴일-처리)
6. [나머지 HTML 템플릿 5개](#6-나머지-html-템플릿-5개)
7. [위클리 전용 로직](#7-위클리-전용-로직)
8. [main.py 최종 업데이트](#8-mainpy-최종-업데이트)
9. [GitHub Actions 최종본](#9-github-actions-최종본)

---

## 1. 스케줄 타이밍 조정

10분 전에 Actions 시작 → 데이터 수집·분석·PDF 생성 → 정각에 Slack 발송

```
발송 시간    Actions 시작   UTC cron (시작 기준)
새벽 6:00   05:50          0 20 * * 2-6
오전 8:00   07:50          50 22 * * 1-5
오후 12:00  11:50          50 2  * * 2-6
오후 4:00   15:50          50 6  * * 2-6
밤 11:00    22:50          50 13 * * 1-5
토 오전9:00 08:50          50 23 * * 5
```

Slack 발송 시 `send_at` 파라미터로 정각 예약 발송 처리.

---

## 2. 토큰 사용량 로깅

### utils/token_logger.py

```python
from datetime import datetime

# 환율 기준
KRW_PER_USD = 1500

# 모델별 가격 (USD per 1M tokens)
PRICING = {
    "gemini-2.5-pro": {
        "input":  1.25,
        "output": 10.00,
    },
    "gemini-2.5-flash": {
        "input":  0.30,
        "output": 2.50,
    },
    "grok-4.3": {
        "input":  1.25,
        "output": 2.50,
    },
}

class TokenLogger:
    def __init__(self, report_type: str):
        self.report_type = report_type
        self.started_at  = datetime.now()
        self.records     = []

    def log(self, model: str, agent: str, input_tokens: int, output_tokens: int):
        """API 호출 1회 기록"""
        price = PRICING.get(model, {"input": 0, "output": 0})
        input_cost  = input_tokens  / 1_000_000 * price["input"]
        output_cost = output_tokens / 1_000_000 * price["output"]
        total_usd   = input_cost + output_cost
        total_krw   = total_usd * KRW_PER_USD

        self.records.append({
            "agent":         agent,
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  input_tokens + output_tokens,
            "cost_usd":      round(total_usd, 6),
            "cost_krw":      round(total_krw, 2),
        })

    def summary(self) -> dict:
        """전체 사용량 집계"""
        elapsed = (datetime.now() - self.started_at).seconds

        total_input   = sum(r["input_tokens"]  for r in self.records)
        total_output  = sum(r["output_tokens"] for r in self.records)
        total_tokens  = total_input + total_output
        total_usd     = sum(r["cost_usd"]      for r in self.records)
        total_krw     = total_usd * KRW_PER_USD

        # 모델별 집계
        by_model = {}
        for r in self.records:
            m = r["model"]
            if m not in by_model:
                by_model[m] = {"input": 0, "output": 0, "cost_krw": 0}
            by_model[m]["input"]    += r["input_tokens"]
            by_model[m]["output"]   += r["output_tokens"]
            by_model[m]["cost_krw"] += r["cost_krw"]

        return {
            "report_type":   self.report_type,
            "elapsed_sec":   elapsed,
            "total_input":   total_input,
            "total_output":  total_output,
            "total_tokens":  total_tokens,
            "total_usd":     round(total_usd, 4),
            "total_krw":     round(total_krw, 1),
            "by_model":      by_model,
            "detail":        self.records,
        }

    def print_summary(self):
        """GitHub Actions 로그 마지막에 출력"""
        s = self.summary()
        print("\n" + "="*50)
        print(f"  토큰 사용량 — {self.report_type}")
        print("="*50)
        print(f"  소요 시간:  {s['elapsed_sec']}초")
        print(f"  총 토큰:    {s['total_tokens']:,} "
              f"(입력 {s['total_input']:,} / 출력 {s['total_output']:,})")
        print(f"  총 비용:    ${s['total_usd']} "
              f"≈ {s['total_krw']:,.0f}원 (환율 {KRW_PER_USD}원)")
        print("-"*50)
        for model, stat in s['by_model'].items():
            print(f"  {model}")
            print(f"    토큰: {stat['input']+stat['output']:,} "
                  f"(입력 {stat['input']:,} / 출력 {stat['output']:,})")
            print(f"    비용: {stat['cost_krw']:,.0f}원")
        print("-"*50)
        for r in s['detail']:
            print(f"  [{r['agent']}] {r['model']} "
                  f"| {r['total_tokens']:,}토큰 "
                  f"| {r['cost_krw']:,.0f}원")
        print("="*50 + "\n")
        return s
```

### 에이전트에서 로거 연동 방법

Gemini 응답에서 토큰 추출:

```python
# agents/fundamental.py 수정 예시
def analyze_fundamental(market_data: dict, logger=None) -> dict:
    model    = genai.GenerativeModel(GEMINI_PRO)
    response = model.generate_content(prompt)

    # 토큰 로깅
    if logger and hasattr(response, 'usage_metadata'):
        logger.log(
            model         = GEMINI_PRO,
            agent         = "펀더멘털 애널",
            input_tokens  = response.usage_metadata.prompt_token_count,
            output_tokens = response.usage_metadata.candidates_token_count,
        )

    text = re.sub(r'```json|```', '', response.text).strip()
    return json.loads(text)
```

Grok 응답에서 토큰 추출:

```python
# agents/supply_demand.py 수정 예시
def analyze_supply_demand(market_data: dict, logger=None) -> dict:
    res = client.chat.completions.create(...)

    # 토큰 로깅
    if logger and res.usage:
        logger.log(
            model         = GROK_MODEL,
            agent         = "수급 분석가",
            input_tokens  = res.usage.prompt_tokens,
            output_tokens = res.usage.completion_tokens,
        )

    return json.loads(res.choices[0].message.content)
```

---

## 3. 유틸리티 모듈

### utils/__init__.py

```python
# 비워둬도 됨
```

### utils/helpers.py

```python
import json, re
from datetime import datetime, timedelta

def safe_json_parse(text: str) -> dict:
    """
    Gemini·Grok이 JSON 외에 설명을 붙이는 경우 대비
    어떤 형태로 와도 JSON 추출
    """
    text = text.strip()
    # 코드블록 제거
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*',     '', text)
    text = text.strip()

    # 그대로 파싱 시도
    try:
        return json.loads(text)
    except Exception:
        pass

    # JSON 부분만 추출
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    # 최후 수단 — 빈 딕셔너리 반환
    print(f"[경고] JSON 파싱 실패:\n{text[:200]}")
    return {}

def get_trading_date(offset_days: int = 0) -> str:
    """
    영업일 기준 날짜 반환
    offset_days: 0=오늘, -1=어제, -5=5영업일 전
    """
    d = datetime.now()
    if offset_days < 0:
        moved = 0
        while moved > offset_days:
            d -= timedelta(days=1)
            if d.weekday() < 5:
                moved -= 1
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

def is_market_holiday() -> bool:
    """
    오늘 한국 시장 휴장 여부 확인
    주말은 자동 처리, 공휴일은 리스트로 관리
    """
    today = datetime.now()

    # 주말
    if today.weekday() >= 5:
        return True

    # 한국 공휴일 (연도별로 업데이트 필요)
    holidays_2025 = [
        "20250101",  # 신정
        "20250128",  # 설날 연휴
        "20250129",  # 설날
        "20250130",  # 설날 연휴
        "20250301",  # 삼일절
        "20250505",  # 어린이날
        "20250506",  # 대체공휴일
        "20250603",  # 지방선거일
        "20250606",  # 현충일
        "20250815",  # 광복절
        "20251003",  # 개천절
        "20251006",  # 추석 연휴
        "20251007",  # 추석
        "20251008",  # 추석 연휴
        "20251009",  # 한글날
        "20251225",  # 크리스마스
        "20251231",  # 연말 휴장
    ]
    today_str = today.strftime("%Y%m%d")
    return today_str in holidays_2025

def format_krw(amount_usd: float, rate: int = 1500) -> str:
    """USD → KRW 변환 문자열"""
    krw = amount_usd * rate
    if krw < 1:
        return f"{krw*100:.1f}전"
    elif krw < 1000:
        return f"{krw:.0f}원"
    else:
        return f"{krw:,.0f}원"
```

---

## 4. 에러 핸들링 & 재시도

### utils/retry.py

```python
import time
import functools

def retry(max_attempts: int = 3, delay_sec: int = 10):
    """
    API 호출 실패 시 자동 재시도 데코레이터
    최대 3회, 10초 간격
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    print(f"[재시도 {attempt}/{max_attempts}] "
                          f"{func.__name__} 실패: {e}")
                    if attempt < max_attempts:
                        time.sleep(delay_sec)
            print(f"[최종 실패] {func.__name__}: {last_error}")
            return {}   # 빈 딕셔너리 반환 → 리포트는 계속 진행
        return wrapper
    return decorator
```

에이전트에 적용:

```python
# agents/supply_demand.py 상단에 추가
from utils.retry import retry

@retry(max_attempts=3, delay_sec=10)
def analyze_supply_demand(market_data: dict, logger=None) -> dict:
    ...
```

---

## 5. 주말·공휴일 처리

### main.py 상단에 추가

```python
from utils.helpers import is_market_holiday

def run_report(report_type: str):

    # 주말·공휴일 체크
    if is_market_holiday():
        # 위클리는 토요일에 실행 → 예외 처리
        if report_type == "weekly":
            pass   # 위클리는 토요일에 실행해도 됨
        elif report_type in ["kr_before", "kr_during", "kr_after"]:
            print(f"[스킵] 오늘은 국장 휴장일 — {report_type} 건너뜀")
            return None
        # 미장 리포트는 미국 휴장일 별도 체크 필요
        # 일단은 한국 공휴일과 겹치는 경우만 처리

    print(f"\n[{datetime.now().strftime('%H:%M')}] {report_type} 시작")
    ...
```

---

## 6. 나머지 HTML 템플릿 5개

### 각 템플릿의 차이점

| 파일 | 헤더 색상 | 주요 섹션 추가/제거 |
|------|-----------|---------------------|
| 01_us_after.html | `#3a3480` (보라) | 미국 섹터 흐름 + 국장 영향 예상 |
| 03_kr_during.html | `#6b3e08` (앰버) | 오전 수급 결과 + 테마 온도 변화 |
| 04_kr_after.html | `#2a5209` (초록) | 최종 결산 + 승자·패자 + 내일 준비 |
| 05_us_before.html | `#3a3480` (보라) | 선물 방향 + 프리마켓 + 오늘 밤 이벤트 |
| 06_weekly.html | `#1a1a1a` (다크) | 주간 총정리 + 테마 생존율 + 에이전트 성적표 |

### Cursor에 이렇게 요청

```
02_kr_before.html 을 기반으로 나머지 5개 템플릿을 만들어줘.
각 파일의 차이점:

01_us_after.html
- 헤더 색상: #3a3480
- 헤더 라벨: "미장 장후"
- 섹션: 미국 지수 결과 / 섹터 자금 흐름 / 거래량 TOP5 / 오늘 국장 영향 예상
- 액션박스 색상: purple

03_kr_during.html
- 헤더 색상: #6b3e08
- 헤더 라벨: "국장 장중"
- 섹션: 현재 지수 / 오전 거래량 급등 / 테마 온도 변화 / 오후 예상 방향
- 액션박스 색상: amber

04_kr_after.html
- 헤더 색상: #2a5209
- 헤더 라벨: "국장 장후"
- 섹션: 최종 지수 / 오늘 승자·패자 / 거래량 TOP5 / 내일 준비
- 액션박스 색상: green

05_us_before.html
- 헤더 색상: #3a3480
- 헤더 라벨: "미장 장전"
- 섹션: 선물 방향 / 오늘 밤 이벤트 / 프리마켓 급등 / 주목 테마
- 액션박스 색상: purple

06_weekly.html
- 헤더 색상: #1a1a1a
- 헤더 라벨: "위클리"
- 섹션: 주간 총정리 / 테마 생존율 / 에이전트 성적표 / 다음 주 캘린더
- 액션박스 색상: green
```

---

## 7. 위클리 전용 로직

### weekly_report.py

```python
"""
위클리 리포트 전용 오케스트레이터
- 월~금 5일치 데이터 취합
- 테마 생존율 분석
- 에이전트 주간 성적표
- 다음 주 캘린더
"""
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_PRO
from firebase_client import get_recent
from utils.helpers import get_trading_date, safe_json_parse
from utils.token_logger import TokenLogger
from reports.pdf_generator import generate_pdf
from firebase_client import save_report
from slack_sender import send_report
import json, re, os
from datetime import datetime

genai.configure(api_key=GEMINI_API_KEY)

def run_weekly():
    logger = TokenLogger("weekly")
    print(f"\n[{datetime.now().strftime('%H:%M')}] 위클리 리포트 시작")

    # ── 1. 이번 주 5일치 리포트 데이터 가져오기 ──────────
    print("  이번 주 데이터 취합 중...")
    recent = get_recent(days=7)

    # 일간 리포트만 필터 (위클리 제외)
    daily_reports = [
        r for r in recent
        if r.get("report_type") not in ["weekly"]
    ]

    # ── 2. Gemini Pro 위클리 종합 분석 ───────────────────
    print("  위클리 종합 분석 중...")
    model  = genai.GenerativeModel(GEMINI_PRO)
    prompt = f"""
    너는 주식 투자 전문가 팀의 팀장이야.
    이번 주 5일치 시장 데이터를 종합해서 주간 리포트를 만들어.
    주식 1년차 초보 투자자가 읽는 리포트야. 쉬운 말로.

    [이번 주 일간 리포트 데이터]
    {json.dumps(daily_reports, ensure_ascii=False, default=str)[:5000]}

    포함할 내용:
    1. 이번 주 시장 총정리 — 결국 돈은 어디서 왔고 어디로 갔나
    2. 테마 생존율 — 월요일 주목 테마가 금요일에 살아있나 죽었나
    3. 에이전트 주간 성적표 — 의견이 맞았는지 틀렸는지
    4. 이번 주 핵심 종목 심층 분석
    5. 다음 주 캘린더 — FOMC·실적·지표 발표 일정
    6. 포트폴리오 체크리스트 5개 (스스로 점검용)

    JSON으로만 반환:
    {{
      "report_type":      "weekly",
      "date":             "이번 주 날짜 범위",
      "one_line_summary": "이번 주 핵심 한 줄",
      "weekly_flow": {{
        "money_in":  ["들어온 섹터1", "들어온 섹터2"],
        "money_out": ["빠진 섹터1",  "빠진 섹터2"],
        "reason":    "이유 한 줄"
      }},
      "theme_survival": [
        {{
          "name":    "테마명",
          "status":  "살아있음/식어가는중/사망",
          "weekly_return": "+3.2%",
          "next_week": "다음 주 전망 한 줄"
        }}
      ],
      "agent_scoreboard": [
        {{
          "agent":    "수급 분석가",
          "score":    "4/5",
          "hit_rate": "80%",
          "comment":  "잘한 것 / 틀린 것 한 줄"
        }}
      ],
      "stock_analysis": [...],
      "next_week_calendar": [
        {{
          "date":  "5/20 (월)",
          "time":  "22:30",
          "event": "미국 소비자신뢰지수",
          "importance": "높음"
        }}
      ],
      "portfolio_checklist": [
        "체크 질문1",
        "체크 질문2",
        "체크 질문3",
        "체크 질문4",
        "체크 질문5"
      ],
      "action_items": ["액션1", "액션2", "액션3"],
      "glossary": [
        {{"term": "용어", "definition": "설명"}}
      ]
    }}
    """
    response = model.generate_content(prompt)

    # 토큰 로깅
    if hasattr(response, 'usage_metadata'):
        logger.log(
            model         = GEMINI_PRO,
            agent         = "위클리 오케스트레이터",
            input_tokens  = response.usage_metadata.prompt_token_count,
            output_tokens = response.usage_metadata.candidates_token_count,
        )

    report_data = safe_json_parse(response.text)

    # ── 3. PDF 생성 ───────────────────────────────────────
    print("  PDF 생성 중...")
    date_str = datetime.now().strftime("%y%m%d")
    filename = f"{date_str}_weekly.pdf"
    pdf_path = f"outputs/{filename}"
    os.makedirs("outputs", exist_ok=True)
    generate_pdf(report_data, pdf_path)

    # ── 4. Firebase 저장 ──────────────────────────────────
    print("  Firebase 저장 중...")
    pdf_url = save_report(report_data, pdf_path, filename)

    # ── 5. Slack 발송 ─────────────────────────────────────
    print("  Slack 발송 중...")
    send_report(pdf_url, report_data.get("one_line_summary", ""), "weekly")

    # ── 6. 토큰 요약 출력 ────────────────────────────────
    logger.print_summary()

    print("  [위클리] 완료!")
    return pdf_url
```

---

## 8. main.py 최종 업데이트

기존 main.py에서 아래 내용 추가/수정:

```python
# 상단 import 추가
from utils.helpers   import is_market_holiday, safe_json_parse
from utils.retry     import retry
from utils.token_logger import TokenLogger
from datetime        import datetime
import time

genai.configure(api_key=GEMINI_API_KEY)

# Slack 예약 발송 시간 계산
SEND_TIMES = {
    "us_after":  "06:00",
    "kr_before": "08:00",
    "kr_during": "12:00",
    "kr_after":  "16:00",
    "us_before": "23:00",
    "weekly":    "09:00",
}

def wait_until_send_time(report_type: str):
    """정각까지 대기"""
    target_time = SEND_TIMES.get(report_type)
    if not target_time:
        return
    now      = datetime.now()
    hh, mm   = map(int, target_time.split(":"))
    target   = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    diff_sec = (target - now).total_seconds()
    if 0 < diff_sec <= 600:   # 10분 이내면 대기
        print(f"  정각 발송 대기 중... ({int(diff_sec)}초 남음)")
        time.sleep(diff_sec)

def run_report(report_type: str):
    logger = TokenLogger(report_type)

    # 휴장일 체크
    if is_market_holiday():
        if report_type == "weekly":
            pass
        elif report_type in ["kr_before", "kr_during", "kr_after"]:
            print(f"[스킵] 오늘은 국장 휴장 — {report_type}")
            return None

    print(f"\n[{datetime.now().strftime('%H:%M')}] {report_type} 시작")

    # ... (기존 데이터 수집 / 에이전트 분석 코드)
    # 각 에이전트 호출 시 logger 파라미터 전달:
    # supply = analyze_supply_demand(market_data, logger=logger)
    # momentum = analyze_momentum(market_data, logger=logger)
    # fund = analyze_fundamental(market_data, logger=logger)
    # macro = analyze_macro(indicators, sector_temp, news, logger=logger)
    # risk = analyze_risk(all_ops, market_data, logger=logger)

    # ... (기존 PDF 생성 / Firebase 저장 코드)

    # 정각까지 대기 후 Slack 발송
    wait_until_send_time(report_type)
    send_report(pdf_url, report_data.get("one_line_summary", ""), report_type)

    # 토큰 사용량 로그 출력 (GitHub Actions 로그 마지막)
    logger.print_summary()

    print(f"  [{report_type}] 완료!")
    return pdf_url

if __name__ == "__main__":
    import sys
    report_type = sys.argv[1] if len(sys.argv) > 1 else "kr_before"

    if report_type == "weekly":
        from weekly_report import run_weekly
        run_weekly()
    else:
        run_report(report_type)
```

---

## 9. GitHub Actions 최종본

10분 전 시작 + 모든 워크플로우 동일한 구조.

### .github/workflows/02_kr_before.yml

```yaml
name: 국장 장전 브리핑

on:
  schedule:
    - cron: '50 22 * * 1-5'   # UTC 22:50 = KST 07:50 (10분 전 시작)
  workflow_dispatch:            # 수동 실행 버튼

jobs:
  report:
    runs-on: ubuntu-latest

    steps:
      - name: 코드 체크아웃
        uses: actions/checkout@v4

      - name: Python 3.11 세팅
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 패키지 캐시
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}

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

      - name: 실패 시 Slack 알림
        if: failure()
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          curl -X POST $SLACK_WEBHOOK_URL \
            -H 'Content-type: application/json' \
            -d '{"text": "❌ 국장 장전 브리핑 생성 실패 — GitHub Actions 로그 확인"}'
```

### 전체 cron 스케줄 (10분 전 기준)

```yaml
# 01_us_after.yml
cron: '50 20 * * 2-6'    # UTC 20:50 = KST 05:50

# 02_kr_before.yml
cron: '50 22 * * 1-5'    # UTC 22:50 = KST 07:50

# 03_kr_during.yml
cron: '50 2  * * 2-6'    # UTC 02:50 = KST 11:50

# 04_kr_after.yml
cron: '50 6  * * 2-6'    # UTC 06:50 = KST 15:50

# 05_us_before.yml
cron: '50 13 * * 1-5'    # UTC 13:50 = KST 22:50

# 06_weekly.yml
cron: '50 23 * * 5'      # UTC 23:50 (금) = KST 08:50 (토)
```

---

## 최종 파일 구조 (전체)

```
D:\project\stockreport\
│
├── agents/
│   ├── __init__.py
│   ├── supply_demand.py
│   ├── momentum.py
│   ├── fundamental.py
│   ├── macro.py
│   └── risk.py
│
├── data/
│   ├── __init__.py
│   ├── us_market.py
│   ├── kr_market.py
│   └── grok_realtime.py
│
├── utils/                    ← 이 파일에서 추가
│   ├── __init__.py
│   ├── token_logger.py       ← 토큰 사용량 로깅
│   ├── helpers.py            ← safe_json_parse, 공휴일 처리
│   └── retry.py              ← API 재시도
│
├── reports/
│   ├── __init__.py
│   ├── pdf_generator.py
│   └── templates/
│       ├── base.html
│       ├── 01_us_after.html
│       ├── 02_kr_before.html
│       ├── 03_kr_during.html
│       ├── 04_kr_after.html
│       ├── 05_us_before.html
│       └── 06_weekly.html
│
├── .github/workflows/
│   ├── 01_us_after.yml
│   ├── 02_kr_before.yml
│   ├── 03_kr_during.yml
│   ├── 04_kr_after.yml
│   ├── 05_us_before.yml
│   └── 06_weekly.yml
│
├── main.py
├── weekly_report.py          ← 이 파일에서 추가
├── config.py
├── firebase_client.py
├── slack_sender.py
├── .env
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## GitHub Actions 로그 출력 예시

```
==================================================
  토큰 사용량 — kr_before
==================================================
  소요 시간:  487초
  총 토큰:    48,320 (입력 38,140 / 출력 10,180)
  총 비용:    $0.1523 ≈ 228원 (환율 1500원)
--------------------------------------------------
  gemini-2.5-pro
    토큰: 31,240 (입력 24,100 / 출력 7,140)
    비용: 179원
  grok-4.3
    토큰: 17,080 (입력 14,040 / 출력 3,040)
    비용: 49원
--------------------------------------------------
  [수급 분석가] grok-4.3      | 8,420토큰 | 24원
  [모멘텀 트레이더] grok-4.3  | 8,660토큰 | 25원
  [펀더멘털 애널] gemini-2.5-pro | 9,840토큰 | 57원
  [매크로 전략가] gemini-2.5-pro | 9,120토큰 | 53원
  [리스크 매니저] gemini-2.5-pro | 6,840토큰 | 40원
  [오케스트레이터] gemini-2.5-pro | 5,440토큰 | 29원
==================================================
```

---

*D:\project\stockreport — 보완 모듈 v1.0 (최종)*
