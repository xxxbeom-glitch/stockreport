# Cursor 통합 명령서 — MVP 3 뉴스/공시 연결 전체 작업

목표는 `weekly_watchlist`에 뉴스/공시 수집 품질 보정부터 판단 결과 연결, Slack/MD 반영, LLM 요약까지 한 번에 구현하는 것이다.  
단, 기존 MVP 1~2 기능은 깨지면 안 된다.

---

## 현재 상태

이미 완료된 것:

- OHLCV 수집 안정화 완료
- `data_check=0`, 25종목 `ok_10d`
- `keep / weaken / caution / remove` 판단 룰 구현
- `remove_candidate` 내부 강도 `strong_remove / review_remove` 구현
- Slack 5섹션 포맷 구현
- 네이버 뉴스/DART 공시 수집 구현
- `data/news/stock_news_YYYY-MM-DD.json` 저장 구현
- `--with-news` 옵션 구현

이번 작업 목표:

```txt
MVP 3-1.5 뉴스 품질 보정
MVP 3-2 판단 결과에 뉴스/공시 연결
MVP 3-3 rule-based 이슈 태깅
MVP 3-4 Slack/MD 반영
MVP 3-5 LLM 요약 연결
MVP 3-6 최종 리포트 구조 정리
```

---

## 절대 지켜야 할 조건

1. 기존 action enum은 유지한다.
   - `keep`
   - `weaken`
   - `remove_candidate`
   - `data_check_needed`

2. `remove_level`, `severity_label`, `reason_code`, `remove_signal_count`, `momentum_weak_count`는 유지한다.

3. 뉴스/공시 수집 실패가 있어도 주간 리포트 생성은 실패하면 안 된다.

4. API 키 값은 절대 로그에 출력하지 않는다.

5. `--with-news`가 없으면 뉴스 수집/연결은 기본 비활성화한다.

6. `--no-llm`이면 뉴스/공시 LLM 요약도 호출하지 않는다.

7. Slack 메시지는 너무 길어지면 안 된다.
   - 종목당 뉴스/공시 이슈는 최대 1개만 표시
   - MD report에는 top 3까지 표시 가능

---

# 1. MVP 3-1.5: 뉴스 품질 보정

현재 네이버 뉴스 수집은 성공하지만, 섹터 기사/단순 언급/동명이인성 뉴스가 top에 섞인다.  
뉴스 관련도 점수와 필터를 보정해라.

## 수정 대상 후보

- `weekly_watchlist/news_collect.py`
- `weekly_watchlist/naver_news_client.py`
- `weekly_watchlist/news_relevance.py`가 없다면 새로 생성
- 관련 테스트 파일

## 요구사항

### 1-1. 직접성 점수 추가

`score_news_relevance(item, stock)` 또는 유사 함수에 아래 로직을 추가한다.

```txt
title에 종목명 포함: +30
description에만 종목명 포함: +10
제목 첫 20자 안에 종목명 포함: +20
종목명이 title/description 모두에 없으면 제외 유지
```

### 1-2. 섹터/테마 기사 감점

아래 조건이면 감점한다.

```txt
title에 종목명이 없고 description에만 여러 종목이 나열된 경우: -20
```

아래 키워드가 title 중심에 있으면 감점한다.

```txt
반도체주
소부장주
테마주
이 시각 시황
브랜드평판
이격도과열
오늘의 IR
주요공시
마감시황
```

감점:

```txt
-15
```

### 1-3. 도메인 편중 제한

종목별 top 3 뉴스에서 같은 도메인이 전부 차지하지 않게 한다.

```txt
종목별 top 3에서 같은 도메인은 최대 2개
가능하면 서로 다른 언론사/도메인 우선
```

### 1-4. 종목 alias/검색 키워드 추가

아래 alias/검색 보정값을 추가한다.

```python
STOCK_NEWS_ALIASES = {
    "099320": ["세트렉아이", "쎄트렉아이"],
    "010620": ["HD현대미포", "현대미포조선"],
    "023160": ["태광 조선기자재", "태광 피팅", "태광 산업용 밸브"],
    "042370": ["비츠로테크 전력", "비츠로테크 방산"],
    "033500": ["동성화인텍 LNG", "동성화인텍 보냉재"],
    "017960": ["한국카본 LNG", "한국카본 보냉재"],
}
```

기존 기본 쿼리:

```txt
{종목명}
{종목명} {섹터키워드}
```

위 alias가 있으면 alias 쿼리를 함께 사용하되, 호출 수가 과도하게 늘지 않게 종목당 최대 3개 쿼리로 제한한다.

### 1-5. quality_flags 추가

각 뉴스 item에 `quality_flags`를 추가한다.

```json
"quality_flags": {
  "direct_title_match": true,
  "description_only_match": false,
  "theme_article": false,
  "possible_name_noise": false,
  "domain_limited": false
}
```

가능하면 boolean dict로 저장한다.

### 1-6. 테스트 추가

아래 테스트를 추가한다.

```txt
태광그룹 뉴스는 태광 조선기자재 종목 top에 우선 노출되지 않음
제목 직접 매칭 뉴스가 description 단순 언급 뉴스보다 위에 옴
같은 도메인 3개가 top 3를 모두 차지하지 않음
quality_flags가 저장됨
```

---

# 2. MVP 3-2: 판단 결과에 뉴스/공시 연결

수집된 `data/news/stock_news_YYYY-MM-DD.json`을 주간 판단 결과에 연결한다.

## 신규/수정 함수

가능하면 아래 함수를 추가한다.

```python
load_stock_news(as_of_date) -> dict
attach_news_to_judgments(judgments, news_data) -> list
select_top_issue_for_slack(stock_judgment) -> dict | None
```

## 연결 방식

각 judgment item에 아래 필드를 추가한다.

```json
"news_context": {
  "naver_news": [],
  "dart_disclosures": [],
  "top_issue": null,
  "issue_tags": []
}
```

매칭 키는 우선순위대로 사용한다.

```txt
ticker 우선
없으면 symbol/name 보조
```

## 실패 처리

- 뉴스 JSON 파일이 없으면 warning 로그만 남기고 계속 진행
- JSON 파싱 실패해도 주간 리포트는 계속 생성
- 종목별 뉴스가 없어도 judgment는 유지

---

# 3. MVP 3-3: Rule-based 이슈 태깅

LLM 전에 코드로 먼저 이슈 태그를 붙인다.

## 태그 목록

```txt
실적
수주
공시
증설
투자
자기주식
목표가
리포트
수급
섹터
소송
방산
조선
반도체
LNG
HBM
AI
```

## 태깅 기준

뉴스 title/description, DART report_nm/matched_keywords를 기준으로 태그를 생성한다.

예:

```txt
단일판매, 공급계약 → 수주, 공시
신규시설투자 → 증설, 투자, 공시
영업(잠정)실적, 실적 → 실적, 공시
자기주식 → 자기주식, 공시
목표주가, 목표가 → 목표가, 리포트
기관 순매수, 외국인 순매수 → 수급
소송 → 소송, 공시
HBM → HBM, 반도체
LNG, 보냉재 → LNG, 조선
방산, 수주잔고 → 방산
```

## top_issue 선정 기준

우선순위:

```txt
DART 중요 공시 > 제목 직접 매칭 뉴스 > 관련도 높은 뉴스 > 섹터 기사
```

DART 공시가 있으면 공시를 우선 top_issue로 둔다.  
단, 소송 같은 리스크 공시는 `risk_issue=true`를 붙인다.

---

# 4. MVP 3-4: Slack/MD 반영

## Slack 반영

Slack에는 종목당 최대 1개 이슈만 짧게 표시한다.

형식:

```txt
• 테크윙 — 복합 약세 신호 5개
  이슈: 공급계약 공시 확인
```

또는

```txt
• 심텍 — 5일 수익·RS·거래대금 중 2개 이상 양호
  이슈: 반도체 기판 수요 기사
```

제약:

```txt
이슈 문구는 45자 이내
뉴스 제목 전체를 길게 붙이지 않음
뉴스가 없으면 이슈 줄 생략
```

## Slack 문구 생성 함수

가능하면 아래 같은 함수로 분리한다.

```python
format_slack_issue_line(news_context) -> str | None
```

## MD report 반영

MD에는 종목별로 뉴스/공시 top 3를 표시한다.

예:

```md
### 테크윙

- 판단: 강한 제외
- 이슈 태그: 수주, 공시, HBM
- 주요 뉴스/공시
  1. [DART] 단일판매ㆍ공급계약체결 — 2026-05-19
  2. [뉴스] 한화운용 HBM ETF 리밸런싱에 테크윙 편입
  3. [뉴스] HBM 테스트 수요 증가 기대
```

리포트 전체 하단에 별도 섹션도 추가한다.

```md
## 종목별 뉴스·공시 이슈
```

---

# 5. MVP 3-5: LLM 요약 연결

LLM 요약은 기본적으로 `--no-llm`이면 호출하지 않는다.

## 목표

수집된 뉴스/공시 top 3를 읽고 종목별 한 줄 해석을 만든다.

예:

```txt
동진쎄미켐: 반도체 소재주 수급은 살아있지만, 섹터 변동성 확대 중
테크윙: 공급계약 공시는 긍정적이나 가격·거래대금 약세가 우선 반영됨
현대로템: 방산 수주 모멘텀은 유지되지만 단기 가격 지표는 약세
```

## 적용 범위

토큰 절약을 위해 처음에는 전체 종목이 아니라 아래 종목만 LLM 요약한다.

```txt
keep 상위 종목
strong_remove 종목
caution_watch 종목
DART 공시가 있는 종목
```

최대 종목 수 제한:

```txt
MAX_LLM_NEWS_SUMMARY_STOCKS = 12
```

## LLM 입력 데이터

원문 전체를 넣지 않는다. 아래만 넣는다.

```txt
종목명
action / reason_code / remove_level
가격 판단 이유
뉴스 title/description top 3
DART report_nm/matched_keywords top 3
issue_tags
```

## LLM 출력 JSON

```json
{
  "ticker": "089030",
  "symbol": "테크윙",
  "issue_summary": "공급계약 공시는 긍정적이나 단기 가격·거래대금 약세가 우세합니다.",
  "issue_tone": "mixed",
  "confidence": "medium"
}
```

`issue_tone` enum:

```txt
positive
negative
mixed
neutral
```

실패하면 rule-based issue line으로 fallback한다.

---

# 6. MVP 3-6: 최종 리포트 구조 정리

주간 리포트 MD 구조를 아래처럼 정리한다.

```md
# 주간 관심종목 재평가

## 요약

## 핵심 유지

## 관찰 약화

## 주의 관찰

## 제외 후보

### 강한 제외

### 제외 검토

## 데이터 확인 필요

## 종목별 뉴스·공시 이슈

## 다음 주 체크포인트
```

`다음 주 체크포인트`는 rule-based로 생성한다.

예:

```txt
- 반도체 소재/장비: 거래대금 회복 여부 확인
- 조선/LNG: 수주·공시 모멘텀 지속 여부 확인
- 방산/우주: 수주잔고·해외계약 뉴스 확인
- strong_remove 종목은 반등 전까지 신규 진입 보류
```

---

# 7. CLI / 실행 옵션

기존 옵션 유지.

```powershell
python scripts/run_weekly_watchlist_update.py --no-llm --no-send --pykrx-only --with-news
```

추가 동작:

- `--with-news`: 뉴스/공시 수집 및 judgment 연결
- `--no-llm`: LLM 뉴스 요약 skip
- `--no-send`: Slack dry-run만 출력

가능하면 뉴스 수집 없이 기존 저장된 JSON만 연결하는 옵션도 추가한다.

```txt
--use-existing-news
```

동작:

```txt
--use-existing-news가 있으면 API 호출 없이 data/news/stock_news_YYYY-MM-DD.json 로드
```

---

# 8. 로그 요구사항

아래 정도만 출력한다.

```txt
[NEWS] configured: naver=True dart=True
[NEWS] collected stocks=25 news_items=73 dart_items=34
[NEWS] attached judgments=25 with_issue=18
[NEWS] llm_summary skipped (--no-llm)
```

키 값은 절대 출력하지 않는다.

---

# 9. 테스트 요구사항

기존 테스트를 모두 유지하면서 아래 테스트를 추가한다.

## 뉴스 품질

```txt
태광그룹 뉴스 노이즈 방지
직접 제목 매칭 우선
description 단순 언급 감점
도메인 편중 제한
quality_flags 저장
```

## 뉴스 연결

```txt
뉴스 JSON 로드 성공
뉴스 JSON 없을 때도 judgment 유지
ticker 기준으로 judgment에 news_context 연결
top_issue 선정 시 DART 중요 공시 우선
```

## 이슈 태깅

```txt
공급계약 → 수주/공시
신규시설투자 → 증설/투자/공시
잠정실적 → 실적/공시
자기주식 → 자기주식/공시
소송 → 소송/공시/risk_issue
```

## Slack/MD

```txt
Slack에는 종목당 top issue 1개만 표시
이슈 문구 45자 이내
뉴스 없으면 이슈 줄 생략
MD에는 top 3 뉴스/공시 표시
```

## LLM

```txt
--no-llm이면 뉴스 요약 호출 안 함
LLM 실패 시 rule-based fallback
LLM 입력 종목 수 MAX_LLM_NEWS_SUMMARY_STOCKS 이하
```

---

# 10. 최종 검증 명령

구현 후 아래를 실행해서 검증한다.

```powershell
python -m unittest tests.test_weekly_watchlist -v
python -m unittest tests.test_stock_news tests.test_dart_client -v
```

가능하면 전체 테스트도 실행한다.

```powershell
python -m unittest discover tests -v
```

실제 dry-run:

```powershell
python scripts/run_weekly_watchlist_update.py --no-llm --no-send --pykrx-only --with-news
```

기존 JSON만 사용해서 연결 테스트:

```powershell
python scripts/run_weekly_watchlist_update.py --no-llm --no-send --pykrx-only --use-existing-news
```

LLM 포함 테스트는 마지막에만 실행한다.

```powershell
python scripts/run_weekly_watchlist_update.py --no-send --pykrx-only --with-news
```

---

# 11. 완료 기준

아래를 만족하면 완료로 본다.

```txt
테스트 전체 통과
뉴스 수집 실패해도 weekly report 생성 유지
뉴스 품질 flags 저장
judgment에 news_context 연결
Slack에 종목별 이슈 1줄 표시
MD에 종목별 뉴스/공시 top 3 표시
--no-llm이면 LLM 호출 없음
LLM 실패 시 fallback 동작
```

---

# 12. 구현 후 보고 형식

작업이 끝나면 아래 형식으로 요약해줘.

```md
## 구현 완료

### 변경 파일
- ...

### 추가 기능
- ...

### 실행 결과
- tests: n passed
- dry-run: success/fail
- news attached: n/25
- slack issue lines: n

### 남은 이슈
- ...
```
