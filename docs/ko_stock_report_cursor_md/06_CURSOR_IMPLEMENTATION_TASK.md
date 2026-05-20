# Cursor 작업 지시서: 국장/미장 AI 리포트 시스템 수정

현재 리포트 템플릿을 AI 기반 주식 리포트 시스템으로 수정한다.
우선 국장 KR 기준으로 구현하고, 미장 US 확장이 가능하도록 구조를 열어둔다.

## 1. 목표

```txt
데이터 수집
→ 데이터 정리
→ AI 분석
→ AI 추론
→ AI 투표
→ 검수/축약
→ 2줄 코멘트 + 라벨 출력
```

## 2. 수정 대상 UI 영역

아래 영역을 AI 출력 영역으로 정리한다.

```txt
마켓 주요 지표 코멘트
섹터 유입·유출 코멘트
투자 의견 라벨 이유
회사 소개 2줄 요약
AI 투표 결과
```

## 3. 데이터 구조

```js
const reportData = {
  marketType: "KR", // "KR" | "US"
  market: {
    kospi: "",
    kosdaq: "",
    nasdaq: "",
    sp500: "",
    dow: "",
    exchangeRate: "",
    interestRate: "",
    usMarket: "",
    futures: "",
    comment: ""
  },
  sectors: {
    inflow: [],
    outflow: [],
    strongThemes: [],
    weakThemes: [],
    relatedStocks: [],
    comment: ""
  },
  stocks: [
    {
      name: "",
      ticker: "",
      market: "KR",
      currentPrice: "",
      targetPrice: "",
      changeRate: "",
      volume: "",
      week52High: "",
      week52Low: "",
      foreignFlow: "",
      institutionFlow: "",
      individualFlow: "",
      news: [],
      disclosure: [],
      label: "",
      labelReason: "",
      companySummary: "",
      aiVotes: [
        {
          engine: "DeepSeek",
          model: "deepseek-v4-pro",
          label: "",
          reason: ""
        },
        {
          engine: "Grok",
          model: "grok-4.3",
          label: "",
          reason: ""
        },
        {
          engine: "Gemini",
          model: "gemini-3.1-pro-preview",
          label: "",
          reason: ""
        }
      ]
    }
  ]
};
```

## 4. 모델 환경변수

```env
DEEPSEEK_DRAFT_MODEL=deepseek-v4-flash
DEEPSEEK_VOTE_MODEL=deepseek-v4-pro
GROK_VOTE_MODEL=grok-4.3
GEMINI_RISK_MODEL=gemini-3.1-pro-preview
GEMINI_SUMMARY_MODEL=gemini-3.1-flash-lite-preview
GEMINI_SUMMARY_FALLBACK_MODEL=gemini-2.5-flash-lite
```

## 5. AI 처리 순서

```txt
1. 한국투자증권/시장/뉴스/공시/수급 데이터 수집
2. marketType 기준으로 KR/US 데이터 정리
3. DeepSeek Flash로 리포트 초안 생성
4. DeepSeek Pro로 데이터 기반 라벨 투표
5. Grok 4.3으로 시장 반응/과열감 투표
6. Gemini 3.1 Pro Preview로 리스크 투표
7. 최종 라벨 결정
8. Gemini Flash-Lite로 모든 UI 문장 2줄 축약
```

## 6. UI 출력 규칙

- 모든 코멘트는 최대 2줄.
- 넘치는 텍스트는 말줄임 처리.
- `입니다/합니다` 어투 금지.
- 메모형 문장 사용.
- 긴 리포트 본문은 화면에 직접 노출하지 않음.
- 사용자는 라벨과 2줄 근거만 빠르게 확인 가능해야 함.

## 7. 라벨 목록

```txt
안 사면 후회함
단기 주목
관망
지금 사기엔 좀...
```

## 8. 금지사항

- 직접 매수 권유 문구 금지.
- 3줄 이상 코멘트 노출 금지.
- 회사 소개 장문 표시 금지.
- UI 레이아웃을 크게 갈아엎지 말 것.
- 현재 템플릿 구조 안에서 AI 출력 필드만 정리.
