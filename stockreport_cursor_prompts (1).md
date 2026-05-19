# StockReport 전체 Cursor 프롬프트 모음

---

## 1. 에이전트 순차 파이프라인 재구성

```
agents/ 전체를 순차 파이프라인으로 재구성해줘.

기존: 5개 에이전트 동시 독립 실행
변경: 순차 실행 (앞 단계 결과가 다음 단계 입력)

실행 순서:
macro → supply_demand → momentum + fundamental → risk → recommender

=== 1단계: macro.py (Michael Chen / 매크로 애널리스트 / Gemini 3.1 Pro) ===

입력:
- 지수 (KOSPI, KOSDAQ, S&P500, NASDAQ)
- 매크로 지표 (달러인덱스, 미국10년금리, VIX, WTI, 구리)
- 섹터 유입/유출

출력 JSON:
{
  "market_phase": "위험회피/중립/강세",
  "market_phase_reason": "한줄 이유",
  "macro_comments": {
    "dollar": "달러 약세, 신흥국 유리",
    "rate": "금리 상승, 주식 부담",
    "vix": "공포 완화, 시장 안정",
    "wti": "경기 둔화 우려, 수요 감소",
    "copper": "소폭 상승, 경기 중립"
  },
  "favorable_sectors": ["에너지", "금융"],
  "unfavorable_sectors": ["반도체", "AI인프라"],
  "watchlist_verdict": {
    "KR": "관심 섹터 전반 불리한 환경",
    "US": "AI전력 섹터 유리한 환경"
  }
}

규칙:
- 실데이터 없으면 N/A, 추측 금지
- 한국어로 출력
- macro_comments는 값에 따라 다르게 생성
  금리 오르면 "주식 부담", 내리면 "주식 호재"
  VIX 20 이상이면 "시장 불안", 이하면 "공포 완화"

=== 2단계: supply_demand.py (James Park / 수급 애널리스트 / Grok + X 실시간 검색) ===

입력:
- 1단계 매크로 결과
- 관심 종목 전체 (KR_WATCHLIST + US_WATCHLIST)
- 각 종목: 현재가, 등락률, 거래량배수, 외국인순매수, 체결강도
- Grok X 실시간 검색 활성화 (grok_client.py 사용)

출력 JSON:
{
  "market_phase": "위험회피",
  "filtered_stocks": [
    {
      "ticker": "010120",
      "name": "LS일렉트릭",
      "market": "KR",
      "reason": "유입 섹터 + 외국인 순매수 + 체결강도 118%",
      "x_sentiment": "X에서 긍정적 언급 증가",
      "score": 85
    }
  ],
  "excluded_stocks": [
    {
      "ticker": "005930",
      "name": "삼성전자",
      "reason": "유출 섹터 + 외국인 대량 매도"
    }
  ]
}

필터링 기준:
- 매크로가 위험회피면 → 유입 섹터 종목만 통과
- 매크로가 강세면 → 전체 스캔
- 외국인 순매수 음수이고 대규모면 → 제외
- 체결강도 90% 이하면 → 제외
- score 계산:
  외국인 순매수 방향 (+30)
  체결강도 100% 이상 (+20)
  거래량 급등 (+20)
  유입 섹터 (+30)

=== 3단계: momentum.py (Chris Yoon / 퀀트 애널리스트 / Grok + X 실시간 검색) ===

입력:
- 2단계 filtered_stocks
- 각 종목: 52주 고저, 현재가, 거래량배수
- Grok X 실시간 검색 활성화

출력 JSON:
{
  "momentum_scores": {
    "010120": {
      "position_52w": "75%",
      "trend": "상승",
      "volume_surge": true,
      "is_x_hot": true,
      "x_momentum_comment": "X에서 AI전력 테마 집중 언급",
      "momentum_score": 80,
      "comment": "52주 75% 위치, 거래량 터지며 상승 중"
    }
  }
}

규칙:
- 52주 위치 90% 이상이면 고점 경고
- 52주 위치 30% 이하면 저점 매수 기회
- 거래량 30배 이상이면 급등 신호

=== 3단계: fundamental.py (이준혁 / 기업 애널리스트 / Gemini 3.1 Pro) ===

입력:
- 2단계 filtered_stocks
- 한국 종목: KIS API PER, PBR, EPS, BPS, 외국인보유비율
- 미국 종목: yfinance per, pbr, revenue, ebitda, net_income, debt_ratio

출력 JSON:
{
  "fundamental_scores": {
    "010120": {
      "per": "18.3",
      "pbr": "2.1",
      "valuation": "적정",
      "financial_summary": "PBR 적정, PER 업종 평균 이하",
      "fundamental_score": 75,
      "comment": "실적 성장세 뚜렷, PBR 적정 수준"
    }
  }
}

규칙:
- PBR 1 이하면 저평가 신호
- 실데이터 없는 수치 절대 생성 금지
- 없으면 N/A

=== 4단계: risk.py (강민서 / 리스크 매니저 / Gemini 3.1 Pro) ===

입력:
- 1단계 매크로 결과
- 2단계 filtered_stocks + score
- 3단계 모멘텀/펀더멘털 점수
- 각 종목: 52주 고저, 현재가, 외국인보유비율

출력 JSON:
{
  "risk_assessments": {
    "010120": {
      "risk_level": "낮음/보통/높음",
      "stop_loss": "230,000원",
      "risk_comment": "고점 대비 -12%, 손절선 230,000원 설정 권장",
      "final_verdict": "매수/홀드/매도",
      "verdict_comment": "외국인 매수 + 실적 성장, 지금 들어가기 좋은 구간"
    }
  },
  "risk_warning": "오늘 조심할 것 한줄",
  "one_line_summary": "전체 시장 한줄 요약"
}

규칙:
- 매크로 위험회피면 리스크 레벨 한 단계 올림
- 52주 고점 대비 -5% 이내면 리스크 높음
- verdict_comment는 쉬운 말로
  "지금 들어가기 좋아요"
  "조금 더 기다리세요"
  "지금 가진 거 들고 기다리세요"

=== 5단계: recommender.py (신규 생성 / Gemini 3.1 Pro) ===

입력:
- 1~4단계 전체 결과
- score 합산

출력 JSON:
{
  "buy_recommendations": [
    {
      "ticker": "010120",
      "name": "LS일렉트릭",
      "market": "KR",
      "price": "243,500원",
      "change_rate": "-3.94%",
      "volume_ratio": "22배",
      "volume_emoji": "🔥",
      "foreign_net": "+342억",
      "conclusion_strength": "118%",
      "position_52w": "-12%",
      "per": "18.3",
      "pbr": "2.1",
      "foreign_ownership": "22.4%",
      "total_score": 82,
      "buy_reason": "AI 데이터센터 전력 수요 급증 최대 수혜주. 외국인 사흘째 순매수 중이고 실적도 성장 중이에요. 지금 들어가기 좋은 구간이에요.",
      "verdict_comment": "한번에 사지 말고 나눠서 들어가세요",
      "stop_loss": "230,000원"
    }
  ],
  "total_scanned": 52,
  "total_passed": 3
}

규칙:
- score 70 이상만 매수 추천
- 최대 5개까지
- buy_reason은 쉬운 말로 3~4줄
- X 데이터와 실데이터 상충하면 실데이터 우선
- 매수 추천 없으면 "오늘은 관망이 답입니다" 출력

=== 환각 방지 공통 규칙 ===
- 실데이터 기반으로만 분석
- 없는 수치 절대 생성 금지
- 확실하지 않으면 N/A
- JSON 스키마 벗어나면 안됨
```

---

## 2. main.py 순차 실행 구조 수정

```
main.py 에서 에이전트 순차 실행 구조로 수정해줘.

기존: 각 에이전트 독립 실행
변경: 순차 실행 (앞 단계 결과가 다음 단계 입력)

순서:
1. 데이터 수집
   kr_data = get_kr_market_data()
   us_data = get_us_market_data()
   watchlist_data = get_watchlist_snapshots()

2. 에이전트 순차 실행
   macro_result = analyze_macro(indicators, sector_temp)
   supply_result = analyze_supply_demand(macro_result, watchlist_data)
   momentum_result = analyze_momentum(supply_result)
   fundamental_result = analyze_fundamental(supply_result)
   risk_result = analyze_risk(macro_result, supply_result, momentum_result, fundamental_result)
   recommendations = get_recommendations(risk_result)

3. report_data 구성
   report_data = {
     "market_phase": macro_result["market_phase"],
     "macro_comments": macro_result["macro_comments"],
     "one_line_summary": risk_result["one_line_summary"],
     "risk_warning": risk_result["risk_warning"],
     "indices": {...},
     "indicators": {...},
     "sector_flow": {...},
     "top_themes": [...],
     "stock_analysis": [...],
     "watchlist_kr": KR_WATCHLIST 전체 현황,
     "watchlist_us": US_WATCHLIST 전체 현황,
     "buy_recommendations": recommendations["buy_recommendations"],
     "company_reports": [...] (장전에만)
   }

4. 슬랙 발송
   send_market_report(report_data, report_type)

5. Firebase 저장
   firebase_client.save(report_data)
```

---

## 3. 데이터 함수 추가

```
아래 함수들 추가해줘.

1. data/us_market.py 에 get_top_volume_us(n=5) 추가
   config.py US_WATCHLIST 종목 스캔
   20일 평균 거래량 대비 오늘 거래량 배수 계산
   상위 n개 반환
   환율 적용 한화 가격 포함
   반환: ticker, name, price_krw, change_rate, volume_ratio

2. data/kr_market.py 에 get_sector_top_stocks(n=3) 추가
   get_sector_trading_value() 결과 섹터별
   pykrx로 해당 섹터 종목 리스트
   거래대금 상위 3개 종목 이름 + 등락률 반환

3. data/us_market.py 에 get_us_financials(ticker) 추가
   yfinance info에서:
   per = trailingPE
   pbr = priceToBook
   revenue = totalRevenue (억원 변환)
   ebitda = ebitda (억원 변환)
   net_income = netIncomeToCommon (억원 변환)
   eps = trailingEps
   debt_ratio = debtToEquity

4. data/kr_market.py 에 get_watchlist_snapshots() 추가
   KR_WATCHLIST 전체 종목 스냅샷
   KIS API로 현재가, 등락률, 거래량, 외국인순매수, 체결강도, PER, PBR 한번에 수집
   반환: {ticker: {name, price, change_rate, volume_ratio, foreign_net, conclusion_strength, per, pbr, foreign_ownership}}

추가 후 각각 터미널 테스트:
python -c "from data.us_market import get_top_volume_us; print(get_top_volume_us(5))"
python -c "from data.kr_market import get_sector_top_stocks; print(get_sector_top_stocks(3))"
python -c "from data.kr_market import get_watchlist_snapshots; print(get_watchlist_snapshots())"
```

---

## 4. GitHub Actions 워크플로 재설계

```
.github/workflows/ 전체 워크플로 재설계해줘.

새 환경변수 추가:
SLACK_BOT_TOKEN
SLACK_CHANNEL_KR
SLACK_CHANNEL_US

스케줄:
01_us_during.yml          → cron: '50 15 * * 2-6'  (새벽 1시 KST)
02_us_close_kr_before.yml → cron: '50 21 * * 2-6'  (오전 7시 KST)
03_kr_during.yml          → cron: '50 3 * * 2-6'   (오후 1시 KST)
04_kr_close_us_before.yml → cron: '50 7 * * 2-6'   (오후 5시 KST)

각 워크플로 env 섹션에 추가:
SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
SLACK_CHANNEL_KR: ${{ secrets.SLACK_CHANNEL_KR }}
SLACK_CHANNEL_US: ${{ secrets.SLACK_CHANNEL_US }}

기존 SLACK_WEBHOOK_URL은 CI 실패 알림용으로 유지.
```

---

## 5. 통합 테스트

```
전체 파이프라인 통합 테스트해줘.

python main.py us_close_kr_before

확인 사항:
1. 에이전트 순차 실행되는지
   macro → supply → momentum/fundamental → risk → recommender

2. 슬랙 국장 채널에 4개 메시지 수신
   메시지 1: 지수 + 매크로
   메시지 2: 섹터 동향 + 거래량
   메시지 3: 관심 섹터 현황
   메시지 4: 매수 추천 + 리스크

3. 매수 추천에 X 실시간 데이터 반영됐는지

4. 오류 없이 끝까지 실행되는지

오류 있으면 수정해줘.
```

---

## 전체 진행 순서

```
1단계: 데이터 함수 추가 (프롬프트 3번)
2단계: 에이전트 파이프라인 재구성 (프롬프트 1번)
3단계: main.py 수정 (프롬프트 2번)
4단계: GitHub Actions 수정 (프롬프트 4번)
5단계: 통합 테스트 (프롬프트 5번)
```
