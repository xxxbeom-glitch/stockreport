# 국장(KR) 리포트 구현 최종 결과 보고서

작성 기준: 저장소 실제 코드 (`d:\project\stockreport`) 및 `00`~`06` 설계 문서 반영 작업 내역.  
대상 UI: `template/kr_market/index.html` (Jinja `template.html` 렌더 결과).  
작성일: 2026-05-21

---

## 1. 전체 작업 결과

| 판정 | **부분성공** |
|------|----------------|

### 판단 근거 (짧게)

- **성공한 부분**: KR 데이터 수집(KIS/pykrx/yfinance), 4엔진 오케스트레이션, AI 모델 중앙 설정(`ai_models.py`), 4라벨 투표·UI 2줄 코멘트 규칙, `kr_market` 어댑터·렌더·`main.py` 연동 골격이 **코드상 존재**함.
- **부분인 이유**:
  - 프로덕션 기본 HTML 출력은 여전히 `reports/templates/*.html` (`pdf_generator.TEMPLATE_MAP`)이며, **Figma `kr_market` UI는 별도 경로**로만 갱신됨.
  - `index.html`은 `build_index.py` / `main.py`(국장 리포트 타입) / `render.py` 실행 시에만 실데이터 반영. API·env 미설정 시 `sample_data.json` 기준 **N/A·fallback** 상태.
  - 문서의 `reportData` JS 스키마·목표가·뉴스/공시·섹터 억원 유입액 등은 **미연동 또는 프록시만** 존재.
  - 라벨 투표는 `label_voting.py` **규칙 기반**이며, 종목별 DeepSeek Pro JSON 투표 API 호출은 **필수 경로가 아님**(키 있을 때만 LLM 보강).
- **실패로 보지 않은 이유**: 핵심 아키텍처는 구현됐으나, E2E·운영 단일 출력·문서 100% 충족은 확인필요.

---

## 2. 진행한 작업 목록 (문서별)

### 00_OVERVIEW.md — 데이터 수집 → 분석 → 추론 → 투표 → 축약 → UI

| 항목 | 내용 |
|------|------|
| 반영 여부 | **부분성공** |
| 수정된 파일 | `data/pipeline.py`, `agents/kr_report_pipeline.py`, `agents/pipeline_runner.py`, `main.py`, `template/kr_market/report_adapter.py` |
| 남은 이슈 | 단일 UI(`kr_market`)와 레거시 5탭 리포트(`reports/templates`) **이중 출력**. `marketType` 필드는 어댑터에 `KR`만, JS `reportData` 객체는 **미생성**. |

---

### 01_DATA_PIPELINE_KR_US.md — KR/US 데이터 파이프라인

| 항목 | 내용 |
|------|------|
| 반영 여부 | **부분성공** (KR 위주) |
| 수정된 파일 | `data/kr_market.py`, `data/kis_client.py`, `data/pipeline.py`, `data/us_market.py`, `agents/watchlist_data.py`, `template/kr_market/report_adapter.py` |
| 남은 이슈 | US는 지수·ETF `sector_flow`만 파이프라인에 병합, **`template/us_market` 미연동**. 목표가·기관/개인·뉴스·공시·텔레그램 **수집 없음**. 섹터 유입 **억원 금액** 대신 등락률(%) 프록시. |

---

### 02_AI_MODEL_POLICY.md — 모델 티어·env 중앙 관리

| 항목 | 내용 |
|------|------|
| 반영 여부 | **성공** (코드 구조) |
| 수정된 파일 | `ai_models.py`, `config.py`, `.env.example`, `agents/deepseek_client.py`, `agents/gemini_client.py`, `agents/grok_client.py`, `agents/llm_router.py`, `utils/token_logger.py` |
| 남은 이슈 | `.env`에 `DEEPSEEK_*` 등 **실제 키·모델명 설정은 환경 의존**. 키 없으면 Gemini/규칙 fallback. **런타임 E2E 검증은 확인필요**. |

---

### 03_AI_AGENTS.md — 4엔진 분리

| 항목 | 내용 |
|------|------|
| 반영 여부 | **성공** (구조), **부분성공** (DeepSeek Vote Engine 명칭) |
| 수정된 파일 | `agents/report_core_engine.py`, `agents/market_pulse_engine.py`, `agents/risk_review_engine.py`, `agents/summary_compress_engine.py`, `agents/kr_report_pipeline.py`, `agents/engine_io.py` |
| 남은 이슈 | 문서의 「DeepSeek Vote Engine」은 `llm_router.generate_vote_json` + `label_voting`(규칙)로 **분산**. Report Draft는 `report_core_engine._build_market_draft` + `company_report`. |

---

### 04_VOTING_AND_LABEL_RULES.md — 4라벨·3 AI 투표

| 항목 | 내용 |
|------|------|
| 반영 여부 | **부분성공** |
| 수정된 파일 | `agents/label_rules.py`, `agents/label_voting.py`, `main.py`, `template/kr_market/template.html`, `template/kr_market/report_adapter.py` |
| 남은 이슈 | 내부 에이전트·Grok 프롬프트는 여전히 **매수/홀드/매도** (`supply_demand.py`, `momentum.py`, `risk.py`). UI 최종 라벨만 4종. `stock_votes.py`는 레거시(5인 분석가) **잔존**, `main`은 `label_voting` 사용. |

---

### 05_UI_COMMENT_RULES.md — 2줄·메모 톤·말줄임

| 항목 | 내용 |
|------|------|
| 반영 여부 | **성공** (템플릿 레이어) |
| 수정된 파일 | `utils/ui_comment.py`, `template/kr_market/comment-ui.js`, `template/kr_market/styles.css`, `template/kr_market/template.html`, `agents/summary_compress.py` |
| 남은 이슈 | `company_report.py` fallback 문구에 **입니다체** 잔존(렌더 전 `format_ui_comment`로 완화). AI 투표 한 줄은 별도 clamp. |

---

### 06_CURSOR_IMPLEMENTATION_TASK.md — kr_market 연동·reportData

| 항목 | 내용 |
|------|------|
| 반영 여부 | **부분성공** |
| 수정된 파일 | `template/kr_market/report_adapter.py`, `template/kr_market/build_index.py`, `template/kr_market/render.py`, `template/kr_market/sample_data.json`, `main.py`, `template/kr_market/template.html` |
| 남은 이슈 | `reportData` JS 상수 **미구현**. `aiVotes`는 템플릿 리스트로 출력. `institutionFlow`/`news`/`targetPrice` **미표시(N/A)**. 미장 **미연결**. |

---

## 3. 변경된 파일 목록

| 파일 | 변경 내용 | 상태 |
|------|-----------|------|
| `ai_models.py` | 모델 정책·티어·KR 엔진 ID 중앙 관리 | 완료 |
| `config.py` | `ai_models` re-export, deepseek 데이터소스 스위치 | 완료 |
| `.env.example` | DEEPSEEK/GROK/GEMINI 모델 env 템플릿 | 완료 |
| `utils/ui_comment.py` | UI 코멘트 2줄·메모 톤·금지 표현 | 완료 |
| `utils/token_logger.py` | 신규 모델 단가 항목 | 완료 |
| `agents/deepseek_client.py` | DeepSeek draft/vote 클라이언트 | 완료 |
| `agents/gemini_client.py` | tier별 Gemini 호출 | 완료 |
| `agents/grok_client.py` | GROK_VOTE_MODEL 기본값 | 완료 |
| `agents/llm_router.py` | draft/vote 라우팅 | 완료 |
| `agents/engine_io.py` | 엔진 I/O TypedDict, kr_ui 헬퍼 | 완료 |
| `agents/report_core_engine.py` | Report Core 엔진 | 완료 |
| `agents/market_pulse_engine.py` | Market Pulse 엔진 | 완료 |
| `agents/risk_review_engine.py` | Risk Review 엔진 | 완료 |
| `agents/summary_compress_engine.py` | Summary Compress 엔진 | 완료 |
| `agents/kr_report_pipeline.py` | 4엔진 KR 오케스트레이션 | 완료 |
| `agents/pipeline_runner.py` | `run_kr_agent_pipeline` 위임 | 완료 |
| `agents/summary_compress.py` | 엔진 위임 + `format_ui_comment` | 완료 |
| `agents/label_rules.py` | 4라벨·금지어·2줄 | 완료 |
| `agents/label_voting.py` | 3 AI 투표·최종 라벨 | 완료 |
| `agents/macro.py` | `generate_vote_json` | 완료 |
| `agents/fundamental.py` | `generate_vote_json` | 완료 |
| `agents/risk.py` | `generate_vote_json`(gemini 우선) | 완료 |
| `agents/recommender.py` | `generate_vote_json` | 완료 |
| `agents/supply_demand.py` | `GROK_VOTE_MODEL` | 완료 |
| `agents/momentum.py` | `GROK_VOTE_MODEL` | 완료 |
| `agents/company_report.py` | draft-tier `generate_draft_json` | 완료 |
| `agents/__init__.py` | 엔진·라벨 export | 완료 |
| `main.py` | 라벨 투표, kr_market `index.html` 렌더 | 완료 |
| `template/kr_market/report_adapter.py` | pipeline → Jinja 컨텍스트 | 완료 |
| `template/kr_market/build_index.py` | CLI 전체 파이프라인 빌드 | 완료 |
| `template/kr_market/render.py` | Jinja + `--live` | 완료 |
| `template/kr_market/template.html` | 동적 바인딩, ai-comment, ai_votes | 완료 |
| `template/kr_market/comment-ui.js` | 클라이언트 2줄·톤 | 완료 |
| `template/kr_market/styles.css` | `.ai-comment` 고정 높이·clamp | 완료 |
| `template/kr_market/sample_data.json` | fallback 미리보기 | 완료 |
| `template/kr_market/index.html` | 렌더 산출물(실행 시 갱신) | 생성형 |
| `reports/templates/_report_core.html` | 4라벨 badge 클래스 보조 | 완료 |
| `agents/stock_votes.py` | (변경 없음·레거시 유지) | 잔존 |
| `reports/pdf_generator.py` | (변경 없음·구 템플릿) | 미연동 |

---

## 4. 데이터 파이프라인 연결 결과 (`template/kr_market/index.html`)

| 항목 | 실제 연결 여부 | 데이터 출처 | fallback 처리 |
|------|----------------|-------------|----------------|
| 시장 지표 | **연결됨** (조건부) | `get_kr_indices()` → `pipeline`/`report_data.indices`; 환율 `USDKRW=X` (`report_adapter._usd_krw_snapshot`) | 값 없으면 **N/A**; `sample_data.json` / 미실행 시 전 항목 N/A |
| 섹터 흐름 | **부분연결** | `macro.favorable_sectors` / `unfavorable_sectors`; KIS `get_kis_sector_trading_value()` 등락률; `get_sector_top_stocks()` 종목명 | 섹터 없으면 placeholder 카드 1개; 유입액 **억원 아님** → `+X.XX%` 또는 N/A |
| 종목 데이터 | **연결됨** (조건부) | `watchlist_data` + `get_stock_snapshot()` (`main._build_stock_row` → `report_adapter._map_stock`) | 현재가·52주·외국인 없으면 **N/A**; 목표가 **항상 N/A** |
| 수급 데이터 | **부분연결** | `foreign_net_buy` / `foreign_net_eok`; supply 점수·Grok 수급(내부) | UI KV에 **외국인 순매수만**; 기관/개인 **미표시** |
| 뉴스/공시 | **미연결** | — | 템플릿·어댑터 필드 없음; `macro.analyze_macro(news=)` **reserved** |
| AI 코멘트 | **연결됨** (조건부) | `pipeline.kr_ui`, `market_phase_reason`, `summary_compress`, `company_reports`, `label_reason` | `AI_COMMENT_FALLBACK` / `COMPANY_SUMMARY_FALLBACK`; `format_ui_comment` + `comment-ui.js` |

### 연결 경로 요약

```text
run_pipeline_as_dict()
  → run_agent_pipeline()  (= run_kr_agent_pipeline)
  → main._build_report_data()
  → build_kr_market_context()
  → template.html → index.html
```

---

## 5. AI 모델 정책 반영 결과

| 역할 | 모델 (문서) | 반영 여부 | 코드 근거 |
|------|-------------|-----------|-----------|
| 초안 분석 | deepseek-v4-flash | **반영** | `ai_models.DEEPSEEK_DRAFT_MODEL`; `report_core_engine._build_market_draft`, `company_report` → `generate_draft_json` |
| 핵심 분석 투표 | deepseek-v4-pro | **반영** (호출은 조건부) | `ai_models.DEEPSEEK_VOTE_MODEL`; `llm_router.generate_vote_json`; macro/fundamental/recommender |
| 시장 반응 투표 | grok-4.3 | **반영** (조건부) | `ai_models.GROK_VOTE_MODEL`; `supply_demand`/`momentum` Grok x_search |
| 리스크 투표 | gemini-3.1-pro-preview | **반영** (조건부) | `ai_models.GEMINI_RISK_MODEL`; `risk_review_engine` → `analyze_risk` + `prefer=gemini` |
| 2줄 축약 | gemini-3.1-flash-lite-preview | **반영** | `GEMINI_SUMMARY_MODEL`; `summary_compress_engine` / `utils.ui_comment` (fallback: `gemini-2.5-flash-lite`) |

- env 오버라이드: `.env.example` 및 `os.getenv("DEEPSEEK_DRAFT_MODEL", ...)` 패턴.
- API 키 없을 때: DeepSeek → Gemini fallback (`llm_router`), Grok/Gemini 단계 **스킵 또는 규칙만** → **확인필요**.

---

## 6. AI 에이전트 구조 결과

| 에이전트 | 역할 | 입력값 | 출력값 | 상태 |
|----------|------|--------|--------|------|
| Report Core Engine | 초안·매크로·펀더멘털·추천 | `ReportCoreInput`: indices, indicators, sector_flow, watchlist, (supply_result, macro_result) | `ReportCoreOutput`: macro, fundamental, recommendations, draft, meta | **성공** |
| Market Pulse Engine | X/수급·모멘텀 | `MarketPulseInput`: macro, watchlist_data | `MarketPulseOutput`: supply, momentum, pulse_summary, meta | **성공** |
| Risk Review Engine | 리스크 검수 | `RiskReviewInput`: macro, supply, momentum, fundamental, watchlist | `RiskReviewOutput`: risk, meta | **성공** |
| Summary Compress Engine | UI 2줄 축약 | `SummaryCompressInput`: fields[], macro, risk | `SummaryCompressOutput`: compressed, macro, risk, meta | **성공** |

오케스트레이션: `agents/kr_report_pipeline.run_kr_agent_pipeline`  
레거시 호환: `pipeline` dict에 `macro`, `supply`, `momentum`, `fundamental`, `risk`, `recommendations`, `engines`, `kr_ui`, `label_votes` 유지.

---

## 7. 라벨/투표 규칙 결과

### 4라벨 사용

`agents/label_rules.py` — `VALID_LABELS`:

- 안 사면 후회함
- 단기 주목
- 관망
- 지금 사기엔 좀...

### 확인 항목

| 확인 항목 | 결과 |
|-----------|------|
| 다른 라벨 제거 여부 | **UI 최종**: 4종만 (`verdict_badge`, `label`). **내부**: 매수/홀드/매도 잔존(supply/risk/Grok) → 라벨 투표로 매핑 |
| AI 투표 결과에 모델명 포함 | **예** — `AiVoteRecord.model`, 템플릿 `ai-vote-model` (`ai_votes_for_template`) |
| 라벨 이유 2줄 제한 | **예** — `sanitize_label_reason`, `format_ui_comment`, CSS `line-clamp: 2` |
| 직접 매수 권유 문구 제거 | **부분** — `FORBIDDEN_PHRASES` / `ui_comment` 필터. AI 프롬프트·fallback 문구에 유사 표현 **잔존 가능** → 렌더 시 필터 |

`main._build_stock_row` → `build_stock_label_votes` → `report_adapter._map_stock` 경로로 `kr_market`에 반영.

---

## 8. UI 코멘트 규칙 결과

| 영역 | 2줄 제한 | 구현 |
|------|----------|------|
| 마켓 주요 지표 코멘트 | **예** | `market_commentary` + `.insight-box.ai-comment` |
| 섹터 유입/유출 코멘트 | **예** | `sector.commentary` + 동일 클래스 |
| 투자 의견 라벨 이유 | **예** | `stock.opinion` + `.opinion-text.ai-comment` |
| 회사 소개 2줄 요약 | **예** | `stock.company_summary` + `.company-box.ai-comment` |

| 확인 항목 | 결과 |
|-----------|------|
| 2줄 초과 시 말줄임 | **예** — `-webkit-line-clamp: 2`, `text-overflow: ellipsis` |
| UI 높이 고정 | **예** — `--ai-comment-block-height` min/max height |
| 입니다/합니다 어투 제거 | **부분** — `ui_comment`/`comment-ui.js` 정규화; 원문 생성 단계 fallback은 **확인필요** |
| 메모형 문장 유지 | **의도 반영** — 짧은 문장·`.` 구분; 품질은 **AI/데이터 의존** |

이중 적용: 서버 `{{ ... \| ui_comment }}` + 클라이언트 `comment-ui.js`.

---

## 9. 실패/미완료 항목

### 아직 안 된 부분

1. **프로덕션 단일 UI**: Slack/Firebase 기본 출력은 `reports/templates/`, Figma UI는 `template/kr_market/` **별도**.
2. **`reportData` JS 객체**: 06 문서 스키마 **미구현**(서버 Jinja 컨텍스트만).
3. **목표가, 기관/개인 수급, 뉴스, 공시**: 수집·KV **없음**(목표가 항상 N/A).
4. **섹터 유입 금액(억원)**: UI 예시와 달리 **등락률 %** 또는 N/A.
5. **미장(`template/us_market`)**: 이번 작업 범위 **제외**.
6. **종목별 LLM 4라벨 투표**: `label_voting`은 파이프라인 결과 **규칙 집계**; DeepSeek Pro가 종목마다 JSON 라벨을 내리는 전용 API 루프는 **없음**.
7. **`stock_votes.py` / 5인 분석가 UI**: 레거시 코드 **잔존**(kr_market 미사용).

### 확인 필요

- `.env`에 `DEEPSEEK_API_KEY`, `GROK_API_KEY`, `GEMINI_API_KEY`, `KIS_APP_KEY` 설정 후 `python template/kr_market/build_index.py` **E2E 실데이터 검증**.
- pykrx/KIS 장애 시 터미널 경고·N/A 비율(실행 로그 기준 확인됨).
- `index.html`이 **sample만** 반영된 채 커밋됐는지(실행 없이 `render.py`만 돌린 경우).

### API/env 때문에 테스트 못 한 부분 (보고서 작성 시)

- DeepSeek/Grok/Gemini **실 API 호출·토큰 비용** 검증은 환경별.
- KIS 실시간·섹터 거래대금 전 종목 **완전 수집** 여부.

---

## 10. 다음 작업 제안 (국장 안정화 → 미장)

1. **국장 E2E 고정**: `build_index.py`를 CI/스케줄에 연결, `index.html` 산출물을 아티팩트로 검증(지수 N/A 비율 게이트).
2. **출력 통합**: `pdf_generator`를 `template/kr_market/template.html`로 전환하거나, Firebase URL을 kr_market HTML로 통일.
3. **데이터 갭**: 목표가(컨센서스 API 또는 명시 N/A), 섹터 억원 유입(KIS 집계), 뉴스/공시(DART/RSS) 순차 추가.
4. **라벨 LLM화(선택)**: `label_voting`에 `generate_vote_json` per engine 호출 옵션.
5. **미장 1단계**: `report_adapter`에 `market_type=US` 분기, `template/us_market` 동일 어댑터 패턴 복제.
6. **06 스키마**: 필요 시 `reportData.json`을 Jinja와 병행 export(프론트 하이드레이션용).

---

## 부록: 실행·확인 방법

### Fallback만 (API 불필요)

```powershell
cd d:\project\stockreport
python template/kr_market/render.py
# → template/kr_market/index.html (sample_data, N/A 다수)
```

### 실데이터 + AI (env 필요)

```powershell
python template/kr_market/build_index.py --report-type us_close_kr_before
# 또는
python main.py us_close_kr_before
```

### 로컬 미리보기

```powershell
cd d:\project\stockreport\template\kr_market
python -m http.server 8080 --bind 0.0.0.0
# http://localhost:8080/index.html
```

---

**생성된 파일 경로:**  
`d:\project\stockreport\docs\ko_stock_report_cursor_md\08_KR_REPORT_FINAL_RESULT.md`
