# stockreport — 프로젝트 상태 요약 (Gemini 인수인계용)

> **작성 목적:** 다른 AI 어시스턴트(Gemini 등)가 이 저장소를 이어받아 개발할 때 필요한 맥락을 한 문서에 모았습니다.  
> **저장소:** `d:\project\stockreport` (GitHub: `xxxbeom-glitch/stockreport`)  
> **최종 반영 시점:** 2026-05-20 기준 코드·워크플로·대화 기록 종합

---

## 1. 프로젝트 개요 및 핵심 목표

### 한 줄 요약
**한국·미국 주식 시장 데이터를 수집하고, 5명의 AI 에이전트가 분석한 결과를 모바일 HTML 리포트로 만들어 Firebase에 올린 뒤 Slack으로 브리핑하는 자동화 파이프라인**입니다.

### 핵심 목표
| 목표 | 설명 |
|------|------|
| **정시 브리핑** | 하루 4회(KST 06/09/17/19시) GitHub Actions로 리포트 생성·발송 |
| **데이터 기반** | pykrx, yfinance, KIS API로 지수·종목·수급·거래량 수집 |
| **에이전트 분석** | 매크로 → 수급 → 모멘텀/펀더 → 리스크 → 매수추천 순차 파이프라인 |
| **배포** | HTML 리포트 공개 URL + Slack **메시지 1개** + 「브리핑 보기」버튼 |
| **사전 필터** | 규칙 기반 `pre_score` 70점 미만 종목은 Grok/Gemini 심층 분석 제외 |

### 사용자-facing 산출물
- **HTML 리포트:** `outputs/YYMMDD_{report_type}.html` (함수명은 `generate_pdf`이나 실제 출력은 HTML)
- **Firebase Storage URL:** Slack 버튼 링크용
- **Slack:** 국면·지수 요약 1통 + Firebase HTML 링크

### 별도 트랙 (프로덕션 미연동)
- **Figma 디자인:** [투자 인사이트 UI](https://www.figma.com/design/CxxvVJfcOcZX6gEHjEp8Vb/%EC%A0%9C%EB%AA%A9-%EC%97%86%EC%9D%8C?node-id=6-142&m=dev)
- **실험 템플릿:** `template/kr_market/` — 더미 데이터·36px 로고 플레이스홀더, `main.py`와 **아직 연결 안 됨**

### 참고 문서 (루트 README 없음)
| 파일 | 내용 |
|------|------|
| `STOCKREPORT_DATA.md` | 데이터 소스·KIS·pykrx |
| `STOCKREPORT_AGENTS.md` | 에이전트 역할·JSON 스키마 |
| `STOCKREPORT_FINAL.md` | 전체 설계 (일부 스케줄은 코드와 불일치 가능) |
| `stockreport_cursor_prompts (1).md` | 초기 프롬프트·스펙 |
| `template/kr_market/README.md` | Figma kr_market 템플릿 스키마 |

---

## 2. 기술 스택

### 런타임·언어
- **Python 3.11** (GitHub Actions `setup-python@v5`)
- **의존성:** `requirements.txt`

```
python-dotenv, requests, openai, google-generativeai, google-genai,
yfinance, pykrx, firebase-admin, jinja2
```

> PDF 생성 라이브러리(WeasyPrint 등)는 **미사용**. `generate_pdf`는 HTML 저장 별칭입니다.

### 백엔드 / 오케스트레이션
- **단일 프로세스 Python** (FastAPI/Django 없음)
- **스케줄러:** GitHub Actions `cron` + `workflow_dispatch`
- **로컬 실행:** `python main.py {report_type}`

### 데이터베이스
- **주 저장:** Firebase Firestore 컬렉션 `reports` (메타데이터)
- **파일 저장:** Firebase Storage (`text/html` 업로드)
- **폴백:** `outputs/report_history.jsonl` (Firebase 미설정 시)
- **캐시:** `outputs/` (KIS 토큰 등, gitignore)

### 외부 API·서비스

| 구분 | 기술 | 모듈 | 용도 |
|------|------|------|------|
| KR 시장 | **pykrx** | `data/kr_market.py`, `data/stock_discovery.py` | 지수, OHLCV, PER/PBR, 발굴, 외국인 순매수 |
| KR 실시간 | **KIS OpenAPI** | `data/kis_client.py` | 가격, 체결강도, 업종 거래대금, 52주 고저 |
| US 시장 | **yfinance** | `data/us_market.py`, `data/sources.py` | 지수, ETF, 거래량, PER/PBR |
| US 섹터 | **yfinance ETF** | `data/sector_flow.py` | SPDR 11 + AI ETF 온도 |
| 수급·모멘텀 AI | **Grok (x.ai)** | `agents/grok_client.py` | `responses.create` + **`tools: x_search`** (X 실시간) |
| 분석·리스크 AI | **Google Gemini** | `agents/gemini_client.py` | JSON 구조화 응답 (macro, fundamental, risk, company, weekly) |
| 배포 | **Firebase Admin** | `firebase_client.py` | Storage + Firestore |
| 알림 | **Slack Web API** | `slack_sender.py` | `chat.postMessage` (Bot Token) |
| 예약 | **eBest** | `config.py` only | 키만 정의, **미구현** |

### Grok 호출 방식 (중요)
- `chat.completions`만으로는 X 검색 OFF
- `search_parameters` / `live_search` → **HTTP 410 deprecated**
- **정식 경로:** `client.responses.create(..., tools=[{"type": "x_search"}])`  
  → `agents/grok_client.py` `grok_x_search_json()`

### 프론트엔드 / UI
- **프로덕션 리포트:** Jinja2 HTML (`reports/templates/`)
- **스타일:** 모바일 max-width 390px, Pretendard (CDN + `reports/static/`)
- **실험 UI:** `template/kr_market/` (정적 CSS, Figma 맞춤)

### 인프라
- **GitHub Actions:** 4 workflow + `test_html.yml`
- **Secrets:** Gemini, Grok, Slack, Firebase, KIS, KRX, Webhook

---

## 3. 시스템 아키텍처 및 주요 폴더/파일 구조

### 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions (cron / manual)                │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  main.py :: run_report(report_type)                              │
│    1) is_market_holiday() → 일부 타입 스킵                       │
│    2) data.run_pipeline_as_dict()     ← 시장 raw 데이터            │
│    3) agents.run_agent_pipeline()     ← 5 에이전트 + 추천         │
│    4) _build_report_data()            ← Jinja payload             │
│    5) reports.generate_pdf()          ← HTML 파일                 │
│    6) firebase_client.save_report()   ← Storage URL               │
│    7) wait_until_send_time()          ← KST 정각 대기(≤10분)      │
│    8) slack_sender.send_report()      ← 1메시지 + 버튼           │
└─────────────────────────────────────────────────────────────────┘
```

### 디렉터리 맵

```
stockreport/
├── main.py                 ★ 일일 리포트 진입점
├── weekly_report.py        ★ 주간 리포트 (Firebase 7일 + Gemini)
├── mock_report.py          ★ API 없이 E2E 테스트
├── config.py               ★ env, 워치리스트, 임계값, ETF 맵
├── firebase_client.py      ★ Storage/Firestore/로컬 JSONL
├── slack_sender.py         ★ Slack 단일 메시지 + Block Kit 버튼
│
├── data/
│   ├── pipeline.py         ★ run_pipeline_as_dict() — 수집 오케스트레이션
│   ├── kr_market.py        KR 지수·종목·PER/PBR·거래량
│   ├── us_market.py        US 지수·거래량·재무
│   ├── kis_client.py       KIS API 래퍼·토큰 캐시
│   ├── sector_flow.py      US 섹터 ETF 스캔
│   ├── stock_discovery.py  동적 종목 발굴 (pykrx)
│   ├── sources.py          yfinance/pykrx 어댑터
│   └── models.py           PipelineResult, SourceStatus
│
├── agents/
│   ├── pipeline_runner.py  ★ run_agent_pipeline() 순서 정의
│   ├── watchlist_data.py     build_watchlist_data() — KR/US 워치리스트 스냅샷
│   ├── scorer.py             pre_score 70점 필터
│   ├── stock_votes.py        HTML용 5에이전트 코멘트·투표
│   ├── macro.py              Michael Chen
│   ├── supply_demand.py      James Park + Grok
│   ├── momentum.py           Chris Yoon + Grok
│   ├── fundamental.py        이준혁 + Gemini
│   ├── risk.py               강민서 + Gemini, 손절가
│   ├── recommender.py        매수 추천 (total_score ≥ 70)
│   ├── company_report.py     Gemini 종목 브리핑
│   ├── gemini_client.py      generate_gemini_json()
│   ├── grok_client.py        grok_x_search_json()
│   ├── profiles.py         AGENT_PROFILES 표시명
│   └── common.py             fmt_krw, format_analyst_comment, compute_stop_loss
│
├── reports/
│   ├── pdf_generator.py    ★ render_html(), TEMPLATE_MAP
│   └── templates/
│       ├── base.html         레이아웃·탭·CSS
│       ├── _report_core.html   5탭 본문 (시장/테마/종목/매수/리스크)
│       └── 01~06_*.html      report_type별 extends
│
├── template/kr_market/     ⚠ Figma 실험 (main 미연동)
│   ├── index.html, template.html, styles.css
│   ├── sample_data.json, render.py
│
├── utils/
│   ├── token_logger.py     Gemini/Grok 비용 로그
│   ├── helpers.py          is_market_holiday, safe_json_parse
│   └── formatters.py       foreign_net_eok 등
│
├── outputs/                gitignore — HTML, history, KIS cache
├── .github/workflows/      01~04 스케줄 + test_html
└── docs/
    └── PROJECT_HANDOFF_GEMINI.md  ← 본 문서
```

### 핵심 파일 역할 (상세)

| 파일 | 핵심 함수/상수 | 역할 |
|------|----------------|------|
| `main.py` | `run_report`, `_build_report_data`, `_build_stock_row`, `TARGET_TIMES` | 전체 오케스트레이션, HTML payload 조립 |
| `data/pipeline.py` | `run_pipeline`, `run_pipeline_as_dict` | 소스 상태·섹터·발굴·지수·매크로 지표 |
| `agents/pipeline_runner.py` | `run_agent_pipeline` | 에이전트 1~8단계 실행 |
| `reports/pdf_generator.py` | `render_html`, `TEMPLATE_MAP`, `generate_pdf` | Jinja 렌더 → HTML 파일 |
| `firebase_client.py` | `save_report`, `get_recent`, `_upload_to_storage` | 업로드·공개 URL·Firestore |
| `slack_sender.py` | `send_market_report`, `build_summary_message`, `resolve_slack_channel` | 1메시지 Slack |
| `agents/scorer.py` | `SCORE_THRESHOLD=70`, `split_watchlist_by_score` | LLM 전 사전 필터 |
| `agents/stock_votes.py` | `resolve_stock_agent_vote` | 종목별 5에이전트 의견(3문장 구어체) |

---

## 4. 주요 기능 구현 상태

### ✅ 완료·운영 중

| 기능 | 상태 | 비고 |
|------|------|------|
| 4회 일일 리포트 스케줄 | ✅ | `.github/workflows/01~04` |
| 데이터 파이프라인 (KR/US 지수·지표·발굴) | ✅ | KIS 없으면 pykrx/yfinance 폴백 |
| 5에이전트 순차 파이프라인 | ✅ | `pipeline_runner.py` |
| pre_score 70 필터 | ✅ | `scorer.py` |
| Grok X 검색 (supply/momentum) | ✅ | `responses.create` + x_search |
| Gemini (macro/fundamental/risk/company) | ✅ | 키 없으면 rules-only 폴백 |
| HTML 5탭 리포트 | ✅ | `_report_core.html` |
| Firebase HTML 업로드 | ✅ | UBLA 시 공개 URL 제한 가능 |
| Slack 1메시지 + 브리핑 버튼 | ✅ | `send_market_report` |
| KST 발송 시각 대기 | ✅ | `wait_until_send_time` (최대 600초) |
| 종목별 에이전트 코멘트 (3문장) | ✅ | `stock_votes.py` + 프롬프트 |
| 손절가 자동 (현재가×0.94) | ✅ | `risk.py`, `compute_stop_loss` |
| PER/PBR KR (pykrx) | ✅ | `get_kr_fundamentals` |
| 주간 리포트 코드 | ✅ | `weekly_report.py` (Actions cron **없음**) |
| mock E2E | ✅ | `mock_report.py`, `test_html.yml` |

### 🟡 부분 완료 / 병행 트랙

| 기능 | 상태 | 비고 |
|------|------|------|
| Figma `template/kr_market` | 🟡 더미만 | `main.py`·`pdf_generator` 미연동 |
| `build_msg1~4` (Slack 4통) | 🟡 코드만 잔존 | **발송 경로에서는 미사용** |
| 레거시 report_type | 🟡 | `kr_before`, `us_after` 등 템플릿 매핑만 존재 |
| eBest API | ❌ 미구현 | config만 |
| PDF 파일 출력 | ❌ | HTML만 |
| weekly GitHub Actions | ❌ | 수동/`python main.py weekly` |

### HTML 리포트 탭 구조 (`_report_core.html`)
1. **시장요약** — 국면, 지수, 매크로 지표, 섹터 유입/유출  
2. **핫테마** — 거래량 상위 5  
3. **종목분석** — 관심종목 현황 + 에이전트 5명 표 (사전점수 **UI 노출 제거됨**)  
4. **매수추천** — score 70+  
5. **리스크** — 경고, 체크리스트, 용어사전  

---

## 5. 핵심 데이터 흐름

### 5.1 수집 단계 (`data.run_pipeline_as_dict`)

```
get_source_statuses()          # yfinance/pykrx/gemini/grok/slack/firebase/kis enabled 여부
scan_us_sector_flow()          # US ETF 5일 수익률·거래량 → sector_flow[]
discover_dynamic_stocks()      # pykrx 발굴 → discovered_stocks[] (거래량배수 등)
get_kr_indices() / get_us_indices()
get_indicators()               # 달러, US10Y, VIX, WTI, 구리 (yfinance)
```

**출력 dict 키:** `source_statuses`, `sector_flow`, `discovered_stocks`, `indices`, `market_indicators`, `warnings`

### 5.2 에이전트 단계 (`run_agent_pipeline`)

```
watchlist_data = build_watchlist_data(market_data)
  └ KR: get_stock_snapshot, _kr_volume_ratio, _kr_fundamentals, get_conclusion_strength
  └ US: yfinance history, get_us_financials

agent_stocks, below = split_watchlist_by_score(all_stocks, threshold=70)

macro = analyze_macro(indices, indicators, sector_flow)     # Gemini optional
supply = analyze_supply(macro, agent_watchlist)              # rules + Grok x_search
momentum = analyze_momentum(supply, watchlist)                # rules + Grok
fundamental = analyze_fundamental(supply, watchlist)        # PER/PBR + Gemini
risk = analyze_risk(macro, supply, momentum, fundamental, watchlist)  # stop_loss
recommendations = get_recommendations(...)                   # risk verdict 매수 + score
```

### 5.3 리포트 payload (`_build_report_data`)

- `macro` → `market_phase`, `sector_flow.hot/cold`, `macro_comments`
- `recommendations` → `buy_recommendations`
- `pipeline.watchlist_data` → `watchlist_by_theme`, `agent_stocks`
- `get_top_volume_kr/us` → `volume_leaders_ranked`
- `_build_stock_row` × N → `stock_analysis` (5에이전트 `agent_votes`)
- `us_close_kr_before` / `kr_during` → `company_reports` (Gemini)

### 5.4 렌더·배포

```
reports.generate_pdf(report_data, "outputs/260520_us_close_kr_before.html")
  → jinja2 render TEMPLATE_MAP[report_type]  # 예: 02_kr_before.html

firebase_client.save_report({ report_data, file_path, report_type })
  → Storage: reports/YYYY/MM/DD/{filename}.html
  → make_public() → https://storage.googleapis.com/... (실패 시 gs://)

slack_sender.send_report({ report_data, report_type, pdf_url })
  → build_summary_message()  # 국면 + 지수 2줄
  → Block: "브리핑 보기" url=pdf_url
```

### 5.5 Slack 채널 라우팅

| report_type | 채널 |
|-------------|------|
| `us_close_kr_before`, `kr_during` | `SLACK_CHANNEL_US` (미국 마감·국장 장전 등) |
| `kr_close_us_before`, `us_during` | 설정에 따라 KR/US — `resolve_slack_channel()` 참고 |

> **주의:** `us_close_kr_before`는 **국장 장전** 리포트이나 Slack은 **US 채널**로 매핑되어 있음 (`KR_SLACK_CHANNEL_TYPES` / `US_SLACK_CHANNEL_TYPES` in `slack_sender.py`).

### 5.6 스케줄 ↔ report_type

| Workflow | KST 목표 | UTC cron | CLI |
|----------|----------|----------|-----|
| 미장 마감 브리핑 | 06:00 | `50 20 * * 1-5` | `us_close_kr_before` |
| 국장 개장 브리핑 | 09:00 | `50 23 * * 1-5` | `kr_during` |
| 국장 마감 브리핑 | 17:00 | `50 7 * * 2-6` | `kr_close_us_before` |
| 미장 개장 브리핑 | 19:00 | `50 9 * * 2-6` | `us_during` |

Actions는 cron **약 10분 전** 시작 → `wait_until_send_time()`으로 정각 맞춤.

---

## 6. 현재 이슈·버그·다음 단계 (To-Do)

### 알려진 이슈 / 운영 리스크

| 이슈 | 영향 | 위치 |
|------|------|------|
| **Firebase UBLA** | `make_public()` 실패 시 `gs://`만 반환 → Slack 버튼·모바일 브라우저 접근 불가 | `firebase_client._upload_to_storage` |
| **pykrx 불안정** | `get_index_ohlcv` 컬럼 오류, 외국인 순매수 length mismatch, 장전 빈 데이터 | `kr_market.py`, `watchlist_data.py` |
| **지수 N/A** | KIS/pykrx 모두 실패 시 HTML·Slack에 N/A | 로그: `[WARN] indices contain N/A` |
| **휴장 스킵** | 고정 holiday set, 연간 수동 갱신 필요 | `utils/helpers.is_market_holiday` |
| **Figma add_figma_file** | WebP 디코딩 오류 (`view_node`는 성공) | MCP 제한 |
| **문서·코드 스케줄 불일치** | `STOCKREPORT_FINAL.md` 8회 언급 vs 실제 4 workflow | 문서 정리 필요 |
| **Grok deprecated API** | 410 on old search params | `grok_client.py` 주석 |
| **위험회피 시 buy=0** | recommender가 risk `final_verdict!=매수` 제외 | 비즈니스 로직상 정상일 수 있음 |

### 권장 To-Do (우선순위)

1. **`template/kr_market` 프로덕션 연동**  
   - `_build_report_data()` → `sample_data.json` 스키마 매핑  
   - 또는 Figma UI를 `reports/templates`로 통합  
2. **Firebase 공개 URL 보장**  
   - UBLA 버킷이면 signed URL 또는 Firebase Hosting 검토  
3. **`.env.example` 추가**  
   - Gemini 인수인계·로컬 셋업용 (값 없이 키 이름만)  
4. **weekly Actions workflow** 추가 (선택)  
5. **`template/kr_market` git 추적** — 현재 untracked일 수 있음  
6. **Slack 채널 매핑 검토** — `us_close_kr_before` → KR 채널 여부 제품 결정  
7. **루트 README.md** — 본 문서 링크 + 빠른 시작  
8. **레거시 `build_msg1~4` 정리** — 사용 안 하면 deprecated 표시 또는 삭제  

---

## 7. 수정 시 규칙 · 건드리면 안 되는 것

### 절대 커밋·노출 금지
| 항목 | 이유 |
|------|------|
| `.env`, `.env.*` | API 키 (`.gitignore`) |
| `*.json` (Firebase SA 등) | `.gitignore`가 `package.json` 외 전부 차단 |
| `outputs/` | 리포트·토큰 캐시 |
| `cole-c3f96-firebase-adminsdk-*.json` | 서비스 계정 (로컬만, Actions는 `FIREBASE_SERVICE_ACCOUNT` secret) |

### 신중히 변경 (파이프라인 깨짐 위험)

| 파일/설정 | 이유 |
|-----------|------|
| `agents/pipeline_runner.py` 실행 순서 | macro→supply→momentum/fundamental→risk→recommendations 의존성 |
| `agents/scorer.SCORE_THRESHOLD` (70) | supply 이후 agent_watchlist 크기·비용에 직결 |
| `agents/grok_client.py` x_search 호출 방식 | 잘못 바꾸면 X 검색 OFF |
| `slack_sender.send_market_report` 단일 발송 | 제품 요구사항: 1메시지+버튼 |
| `config.KR_WATCHLIST` / `US_WATCHLIST` | 전 에이전트·HTML 관심종목 범위 |
| `reports/pdf_generator.TEMPLATE_MAP` | report_type별 HTML 깨짐 |
| `.github/workflows` cron | 운영 발송 시각 변경 시 KST·UTC 둘 다 확인 |

### 사용자/저장소 규칙 (대화·user rules)
- **git commit / push:** 사용자가 **명시적으로 요청할 때만**
- **git config** 변경 금지
- **force push main/master** 금지
- **최소 diff** — 요청 범위 밖 리팩터링 금지
- **응답 언어:** 사용자 대화는 한국어

### 코딩 컨벤션 (기존 코드 따르기)
- `safe_float`, `fmt_krw`, `format_analyst_comment` — `agents/common.py` 재사용  
- 동적 import 패턴: `main._safe_call_with_default("save_report", ...)` — firebase/slack 없어도 실행 계속  
- 에이전트 코멘트: **숫자만 나열 금지**, 3문장 구어체 (`ANALYST_VOICE_RULES`)  
- HTML: 이모지·아코디언 없음, Pretendard, 390px 모바일 (`base.html`)  
- 사전점수: **내부만** (`pre_score`), HTML에 표시하지 않음  

### 건드려도 되는 확장 포인트
- `template/kr_market/` — 실험 전용  
- `mock_report.py`, `scripts/verify_template.py`  
- `STOCKREPORT_*.md` 문서  
- `slack_sender.build_msg1~4` (현재 미사용 레거시)  

---

## 부록 A: 환경 변수 체크리스트

```bash
# AI
GEMINI_API_KEY=
GEMINI_PRO_MODEL=gemini-3.1-pro-preview   # default
GEMINI_FLASH_MODEL=gemini-2.5-flash
GROK_API_KEY=
GROK_MODEL=grok-3
GROK_BASE_URL=https://api.x.ai/v1

# Slack
SLACK_BOT_TOKEN=
SLACK_CHANNEL_KR=
SLACK_CHANNEL_US=
SLACK_WEBHOOK_URL=          # Actions 실패 알림

# Firebase
FIREBASE_STORAGE_BUCKET=
FIREBASE_SERVICE_ACCOUNT=   # JSON string (Actions)
FIREBASE_KEY_PATH=          # 로컬 파일 경로

# KIS / KRX
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=
KRX_ID=                     # pykrx 로그인 (선택)
KRX_PW=
```

---

## 부록 B: 로컬 실행 명령

```bash
pip install -r requirements.txt
# .env 작성 후

python main.py us_close_kr_before
python main.py kr_during
python main.py kr_close_us_before
python main.py us_during
python main.py weekly          # → weekly_report.run_weekly()

# HTML 템플릿만
python scripts/verify_template.py
python mock_report.py

# Figma 실험 템플릿
start template/kr_market/index.html
python template/kr_market/render.py
```

---

## 부록 C: 에이전트 ↔ 파일 매핑

| 표시명 | key | 모듈 | LLM | 출력 키 (pipeline) |
|--------|-----|------|-----|---------------------|
| Michael Chen | macro | `macro.py` | Gemini | `macro` |
| James Park | supply | `supply_demand.py` | Grok | `supply`, `grok_verdicts` |
| Chris Yoon | momentum | `momentum.py` | Grok | `momentum`, `momentum_scores` |
| 이준혁 | fundamental | `fundamental.py` | Gemini | `fundamental`, `fundamental_scores` |
| 강민서 | risk | `risk.py` | Gemini | `risk`, `risk_assessments` |
| (추천) | — | `recommender.py` | Gemini optional | `recommendations` |

---

## 부록 D: 최근 Git 이력 (참고)

- `d22ca2b` — natural Korean analyst comments, HTML pre-score 제거  
- `6b4c2cd` — mobile briefing, Slack button, workflow display names  
- `bff181c` — sequential agent pipeline, Grok X search, workflow reschedule  

---

*이 문서는 코드 스캔·`STOCKREPORT_*.md`·에이전트 대화 기록을 바탕으로 작성되었습니다. 코드 변경 후 스케줄·env·TEMPLATE_MAP은 반드시 재확인하세요.*
