# 10. Cursor 진행 기록

## 현재 상태

**Slack 자동 발송: 장중 관심종목 알림만** (`kr_intraday_slack.yml`).

- 스케줄: KST **09:30 / 10:50 / 13:50 / 14:50** (월~금)
- CI: `python scripts/run_kr_intraday_slack.py --slot <SLOT> --live --send`
- **예전 장시작/장마감 리포트 Slack: OFF** (workflow 비활성 + `main.py`/`slack_sender` 기본 skip)
- 리포트 HTML·kr_market 데이터 생성은 로컬 `main.py` 가능 (Slack 없음)

## 다음 작업 (선택)

- Environment secrets 사용 시 `kr_intraday_slack.yml` 의 `environment:` 이름 확인 후 주석 해제
- workflow_dispatch Preflight 전부 OK 확인 후 스케줄 슬롯 모니터링

---

## 2026-05-21 작업 기록 — Actions secret MISSING 수정

### 원인

`Preflight secrets` step에 `env`가 없고, secrets 매핑이 **다음 step(`Run intraday scan`)에만** 있어서 bash에서 빈 값으로 체크됨.

### 수정 (`kr_intraday_slack.yml`)

- **job 레벨 `env`** 에 필수/optional secrets·vars 일괄 매핑 (이름 통일)
- Preflight: 존재 여부만 `OK` / `MISSING` 출력 (값 미출력)
- optional 키는 MISSING이어도 job 중단 없음
- Environment secrets: `jobs.scan.environment` 주석 + README 안내 (이름은 repo Settings에서 확인 필요)

### 필수 secret 이름

`DEEPSEEK_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_KR`, `KIS_APP_KEY`, `KIS_APP_SECRET`

### 확인 방법

Actions → Run workflow → **Preflight secrets** 로그:

```text
OK DEEPSEEK_API_KEY
OK SLACK_BOT_TOKEN
...
All required secrets present.
```

---

## 2026-05-21 작업 기록 — GitHub Actions workflow 정리

### 삭제한 파일

- `.github/workflows/01_us_close.yml` ([DISABLED] 미장 마감 브리핑)
- `.github/workflows/02_kr_open.yml` ([DISABLED] 국장 개장 브리핑)
- `.github/workflows/03_kr_close.yml` ([DISABLED] 국장 마감 브리핑)
- `.github/workflows/04_us_open.yml` ([DISABLED] 미장 개장 브리핑)

### 남은 workflow (3개)

| 파일 | 이름 | 용도 |
|------|------|------|
| `kr_intraday_slack.yml` | **KR Intraday Slack Scan** | 장중 슬랙 자동 발송 (`--live --send` 유지, 미수정) |
| `kr_market_verify.yml` | KR Market Watchlist Verify | 관심종목 렌더 검증 (Slack 없음) |
| `test_html.yml` | HTML 디자인 테스트 | 템플릿 검증 |

### 확인

- `KR Intraday Slack Scan`: `--live --send` 유지 확인 (변경 없음)
- 멀티 모델 파이프라인·`scripts/run_kr_intraday_slack.py`: 유지

---

## 2026-05-21 작업 기록 — 09:30 Slack 미수신 원인 점검

### 점검 결과 (7항목)

| # | 항목 | 결과 |
|---|------|------|
| 1 | workflow `--live --send` | ✅ 코드에 포함 (`2691467` 이후) |
| 2 | cron KST 09:30/10:50/13:50/14:50 | ⚠️ 기존 `1-5`는 **UTC 월~금** — KST 월요일 09:30(UTC 일요일 00:30)은 **미실행**. 목~금 KST는 해당. **→ `0-4` UTC로 수정** |
| 3 | 최근 push | ✅ `af232c5` 07:23 KST, `2691467` 07:32 KST (09:30 이전 반영됨) |
| 4 | Actions 실행 로그 | ❌ **`kr_intraday_slack.yml` workflow runs = 0** (스케줄·수동 모두 없음) |
| 5 | message_count=0 | 해당 없음 — **실행 자체가 없음** |
| 6 | Slack 발송 실패 | 해당 없음 |
| 7 | `data/logs/kr_slack/2026-05-21.jsonl` | ✅ 있으나 **로컬 테스트** (07:11~07:26) — CI 기록 아님 |

### 주요 원인

**GitHub Actions가 한 번도 실행되지 않았음** (`total_count: 0`).

- 로컬에서 `--live --send`로 보낸 메시지(07:xx)와 혼동 가능
- CI 러너는 종료 시 `data/logs`가 사라져 jsonl이 repo에 남지 않음
- 스케줄 워크플로가 repo에 올라간 뒤에도 **첫 scheduled run이 아직 없었을 가능성** (설정·활성화·UTC 요일 불일치)

### 수정 (`.github/workflows/kr_intraday_slack.yml`)

- cron `1-5` → **`0-4` (UTC)** 로 KST 월~금 장중 슬롯 정합
- `workflow_dispatch` + slot `auto`, preflight secrets, `scan.log` artifact 업로드
- schedule/dispatch 모두 **`--live --send` 고정**

### 운영자 즉시 조치

1. GitHub → Actions → **KR Intraday Slack Scan** → **Run workflow** (slot `0930`, live/send true) — 1회 수동 실행
2. Repo **Settings → Actions → General** 에서 Actions 허용 여부 확인
3. 다음 자동 슬롯(10:50 KST) 전후 실행 이력 확인

---
- HD현대미포(010620) 시세/티커 정합

---

## 2026-05-21 작업 기록 — GitHub Actions 자동 발송 운영 전환

### 수정 파일

- `.github/workflows/kr_intraday_slack.yml`
- `scripts/run_kr_intraday_slack.py`
- `10_progress.md`

### workflow 실행 명령 (운영)

```bash
python scripts/run_kr_intraday_slack.py --slot <0930|1050|1350|1450> --live --send
```

`<SLOT>`은 cron 트리거별 `github.event.schedule` 매핑 (수동 실행 시 `workflow_dispatch` input).

### 자동 발송 시간 (KST, 월~금)

| KST | UTC cron | slot |
|-----|----------|------|
| 09:30 | `30 0 * * 1-5` | 0930 |
| 10:50 | `50 1 * * 1-5` | 1050 |
| 13:50 | `50 4 * * 1-5` | 1350 |
| 14:50 | `50 5 * * 1-5` | 1450 |

### 실제 발송 조건 (변경 없음)

1. KIS/pykrx 라이브 수집 → 규칙 1차 후보 → **DeepSeek** JSON 판단
2. `ai_send_slack=true` 이고 decision ∈ {테스트 진입 검토, 예약가 제안, 관찰 강화, 눌림 진입 가능, 수급 반전 감지}
3. 금지 decision(비추천, 진입 보류 등) → 메시지·발송 없음
4. **SendFilter**: 최대 3건, 당일 동일 티커 중복 발송 제외(예약가 유의미 변경 시 재발송 가능)
5. `result.messages` 비어 있으면 `send_kr_intraday_slack` 호출 안 함

### workflow 보강 내용

- `env`: KIS, KRX, Grok, Gemini, DeepSeek, Slack (기존 Secrets 사용)
- 슬롯: `github.event.schedule` 우선 매핑 (지연 시 KST 시각 fallback)
- `workflow_dispatch`: `live`/`send` 기본 true
- `concurrency`: 슬롯별 중복 실행 방지

### 스크립트 보강

- `--live --send` 시 `운영 모드` 로그
- 발송 0건 → exit 0 (`발송 대상 0건 — 슬랙 미발송`)
- AI 미설정 + `--send` → exit 1

### 다음 확인 사항

- 내일 장중 첫 cron(09:30 KST) Actions 로그에서 `slack send: {'count': N}` 확인
- 당일 중복 발송 스킵(`당일 이미 발송됨`) 동작이 의도와 맞는지 점검
- 010620 라이브 수집 실패가 후보 선정에 영향 없는지 모니터링

---

## 2026-05-21 작업 기록 — 예전 리포트 Slack 발송 비활성화

### 수정 요약

- **Slack 자동 발송 ON**: `kr_intraday_slack.yml` 만 (KST 09:30/10:50/13:50/14:50)
- **Slack 자동 발송 OFF**: `01_us_close`, `02_kr_open`, `03_kr_close`, `04_us_open` (workflow DISABLED stub)
- **CI Slack OFF**: `kr_market_verify.yml` (`--notify-slack` 제거)
- **코드 게이트**: `STOCKREPORT_ALLOW_LEGACY_REPORT_SLACK` 미설정 시 `main.py`·`send_market_report`·`send_kr_watchlist_report_slack` skip
- **유지**: `send_kr_intraday_slack`, 멀티모델 파이프라인, kr_market 렌더

### Workflow 표

| 상태 | 파일 |
|------|------|
| ON | `kr_intraday_slack.yml` |
| OFF | `01_us_close.yml`, `02_kr_open.yml`, `03_kr_close.yml`, `04_us_open.yml` |
| ON (Slack 없음) | `kr_market_verify.yml`, `test_html.yml` |

### 로컬

```bash
python scripts/run_kr_intraday_slack.py --slot auto --live --send   # 장중 알림
python main.py kr_during   # 리포트 생성만, Slack 없음
```

---

## 2026-05-21 작업 기록 — 멀티 모델 E2E 검증 (로컬)

검증 일시: 2026-05-21 (KST, 로컬 `.env` + Secrets 반영 환경)

### 실행 명령·결과 요약

| # | 명령 | exit | 메시지 수 | Slack 발송 |
|---|------|------|-----------|------------|
| 1 | `--slot 0930 --live` | 0 | **2** | **없음** (`--send` 미사용, `slack send` 로그 없음) |
| 2 | `--slot 0930 --live --json` | 0 | **3** | **없음** |
| 3 | `--slot 0930 --live --send` | 0 | **2** | **2건** `ok=True`, `count=2`, `errors=[]` |

※ DeepSeek 판단은 실행마다 비결정적이라 메시지 수·종목이 달라질 수 있음. 구조 검증은 3회 모두 통과.

### 검증 체크리스트

| 항목 | 결과 |
|------|------|
| KIS/pykrx 라이브 수집 | `live 수집 완료 total=25 ok=24 fail=1` (010620 HD현대미포 실패, 기존 이슈) |
| DeepSeek 필수 호출 | `HTTP/1.1 200 OK`, `[kr_intraday_batch] OK provider=deepseek model=deepseek-chat` |
| Grok `configured=True` | CLI·JSON `aux_models.grok.configured: true`, `model: grok-3` |
| Gemini `configured=True` | CLI·JSON `aux_models.gemini.configured: true`, `model: gemini-1.5-flash` |
| Grok 보조 (optional) | `ai_send_slack=true` 종목만 호출; 실행별 `Grok enrich ok=2/2` 또는 `4/4` |
| Gemini polish (optional) | 전건 `gemini_polish.status=fallback`, `reason=Gemini 응답 없음` → **초안 fallback 정상** |
| 메시지 0~3건 제한 | 2~3건 (SendFilter `max 3` 이내) |
| `--send` 없을 때 미발송 | 테스트 1·2: `send_kr_intraday_slack` 미호출 확인 |
| `--send` 시 승인 종목만 | 테스트 3: `274090` 켄코아, `099320` 세트렉아만 `sent: true` |
| 비추천 미발송 | `007810` 코리아써키트, `036930` 주성엔지니어링 → `skip_reason: 발송 금지 decision: 비추천`, `grok_context: null`, Slack 미발송 |
| jsonl grok/gemini 메타 | `data/logs/kr_slack/2026-05-21.jsonl`에 `grok_status`, `grok_context`, `gemini_polish`, `slack_message_draft` 기록 확인 |

### 테스트 1 상세 (`--live` 드라이런)

```text
models primary=True grok=True gemini=True
live 수집: total=25 ok=24 fail=1
DeepSeek: candidates=4 send_slack=2 errors=2
  - [코리아써키트] 발송 금지 decision: 비추천
  - [주성엔지니어링] 발송 금지 decision: 비추천
Grok enrich ok=2/2 (send_slack=true 2종목만)
Gemini: gemini_polished 0/2 (전건 fallback)
messages: 2
```

### 테스트 2 상세 (`--live --json`)

```json
"aux_models": {
  "primary": { "configured": true, "provider": "deepseek", "model": "deepseek-chat" },
  "grok": { "configured": true, "provider": "grok", "model": "grok-3" },
  "gemini": { "configured": true, "provider": "gemini", "model": "gemini-1.5-flash" }
}
"message_count": 3
"ai_errors": []
```

- DeepSeek `send_slack=4` → SendFilter 후 **3건** 메시지 (상한 3 적용 확인)

### 테스트 3 상세 (`--live --send`)

```text
DeepSeek: candidates=4 send_slack=2 (비추천 2건 스킵)
messages: 2
slack send: {'ok': True, 'channel': 'C0B4X9JBK5X', 'count': 2, 'errors': []}
```

**jsonl 발송 기록 (마지막 2행)**

- `274090` 켄코아에어로스페이스: `sent: true`, `grok_context`·`gemini_polish`·`slack_message_draft` 포함
- `099320` 세트렉아이: `sent: true`, 동일 메타 포함
- `007810`/`036930`: `sent: false`, `발송 금지 decision: 비추천`

### 실패·스킵 로그

| 구분 | 내용 |
|------|------|
| 라이브 수집 | `010620` HD현대미포: KIS 0시세·pykrx 미등록 (기존) |
| DeepSeek 스킵 | `비추천` decision → `ai_send_slack=false`, Grok 미호출 |
| Gemini | API 키는 있으나 `gemini-1.5-flash` 응답 없음 → 초안 사용 (의도한 fallback) |
| pykrx WARNING | `get_index_ohlcv_by_date` 컬럼 오류 (수집은 진행) |

### 다음 보완 작업

1. **Gemini polish 실호출**: `AI_SUMMARY_MODEL`을 `GEMINI_SUMMARY_MODEL`(예: `gemini-3.1-flash-lite-preview`)로 변경 후 `gemini_polish.status=ok` 재검증
2. **SDK 마이그레이션**: `google.generativeai` deprecated → `google.genai`
3. **010620** 시세 정합, 기관 수급 필드 보강 (선택)

---

## 2026-05-21 작업 기록 (01~08 일괄)

### 처리한 문서

- 01_watchlist.md ~ 08_cursor_prompt.md

### 수정·추가한 파일

| 구분 | 파일 |
|------|------|
| 관심종목 | `data/kr_watchlist.json`, `data/kr_watchlist.py` |
| 슬랙 v2 | `data/kr_slack_alerts.py`, `agents/kr_intraday_slack/*` |
| 발송 | `slack_sender.py` (`send_kr_intraday_slack`) |
| 실행 | `scripts/run_kr_intraday_slack.py` |
| CI | `.github/workflows/kr_intraday_slack.yml` (유일한 Slack 자동 발송) |
| 진행 | `09_task_queue.md`, `10_progress.md` |

※ 예전 `01~04` 브리핑 workflow는 2026-05-21 삭제됨.

### 작업 내용 (문서별)

**01_watchlist**

- 5섹터·25종목 JSON 고정, 해운 제외
- `validate_watchlist_spec()` 검증 함수
- 세트렉아이 표기 문서 정합 (티커 099320)

**02_message_goal**

- `constants.py`: 발송 허용/금지 상태, 금지 표현, 최대 3건, 조건 없으면 미발송

**03_scan_logic**

- `market_data.py` / `watchlist_pick.py` / `entry_price.py`: 수집→선별→예약가 범위(더미)

**04_agents**

- 6단계 에이전트 모듈 분리 + `pipeline.run_intraday_scan`

**05_schedule**

- 슬롯 `0930|1050|1350|1450`, GitHub Actions cron(KST 기준 슬롯 판별)

**06_slack_message**

- `slack_message.build_slack_message`: 판단 / 진입 관점 / 주의 조건 포맷

**07_system_changes**

- 발송 로그 `data/logs/kr_slack/YYYY-MM-DD.jsonl`
- 당일 중복 발송 방지·예약가 변경 시 재발송 허용
- 앱 리포트(kr_market)는 기존 watchlist 연동 유지

**08_cursor_prompt**

- `scripts/run_kr_intraday_slack.py` CLI 통합
- `agents/kr_intraday_slack/README.md` 안내

### 검증

```text
validate_watchlist_spec() → []
python scripts/run_kr_intraday_slack.py --slot 0930 → messages 0~3건
```

### 이슈/주의사항

- `config.KR_WATCHLIST`는 JSON 직접 로드(순환 import 방지)
- 장중 스캔은 **더미 시드 데이터** — 라이브 API 전환 필요
- GitHub cron은 UTC; 슬롯은 실행 시 `Asia/Seoul` 시각으로 결정

## 2026-05-21 작업 기록 — KIS/pykrx 라이브 연동

### 처리한 항목

- `10_progress.md` 다음 작업: MarketDataAgent 라이브 경로

### 수정·추가한 파일

- `agents/kr_intraday_slack/live_market_data.py` (신규)
- `agents/kr_intraday_slack/market_data.py` (`live`, `tickers` 인자)
- `agents/kr_intraday_slack/pipeline.py` (`live`, `tickers` 전달)
- `scripts/run_kr_intraday_slack.py` (`--live`, `--ticker`)
- `scripts/test_live_watchlist_data.py` (신규 스모크 테스트)
- `agents/kr_intraday_slack/README.md`

### 작업 내용

- KIS `inquire-price`: 현재가·전일종가·당일 고저·누적거래대금 (필드 없으면 pykrx 보완, **조용한 더미 대체 없음**)
- pykrx `get_market_ohlcv` / `get_market_ohlcv_by_date`: OHLC·거래대금·52주 고가·전일종가 보완
- 외국인 순매수: `get_foreign_net_by_ticker` (KIS → pykrx)
- 기관 순매수: pykrx `get_market_trading_value_by_ticker` (미지원 시 WARNING만, `inst_net_eok=None` → 0)
- 거래량비율: 기존 `_kr_volume_ratio` 재사용
- `data_complete=False` + `fetch_errors`에 최종 누락 필드만 기록

### 테스트 명령어

```powershell
# 1종목 (테크윙)
python scripts/test_live_watchlist_data.py --ticker 089030

# 25종목 전체
python scripts/test_live_watchlist_data.py --all

# 장중 스캔 파이프라인(라이브)
python scripts/run_kr_intraday_slack.py --slot 0930 --live
python scripts/run_kr_intraday_slack.py --slot 0930 --live --ticker 089030
```

### 성공/실패 로그 (실행일 2026-05-21, KST)

**1종목 (089030 테크윙)**

```text
INFO kr_intraday.market_data: [089030] KIS 부분 필드 — pykrx로 보완 완료
INFO kr_intraday.market_data: [089030 테크윙] live OK source=kis price=48,000원 tv=41,621,662,875원 foreign_eok=4 inst_eok=None
[SUMMARY] fetched=1 ok=1 fail=0
```

**25종목 전체**

```text
INFO kr_intraday.market_data: [KR INTRADAY] live 수집 완료 slot=0930 total=25 ok=24 fail=1
[SUMMARY] fetched=25 ok=24 fail=1 expected=25
```

**실패 1건**

- `010620` HD현대미포: KIS 현재가·거래대금 **0** 응답, pykrx 당일 OHLC에 티커 없음 → `data_complete=False`, `fetch_errors`: 필수 필드 전체 누락

**공통 WARNING**

- pykrx `get_market_trading_value_by_ticker` 미지원 → 기관 수급 미연동(외국인만)
- `get_trading_date()` probe 시 pykrx index API 컬럼 오류 메시지(수집 자체는 진행)

### 다음 작업

- Actions 워크플로에 `--live` 추가
- 010620 티커·KIS 장중 시세 유효성 점검
- 기관 수급 대체 수집 경로
- 라이브 E2E 슬랙 발송 검증

## 2026-05-21 작업 기록 — DeepSeek LLM 판단 연동

### 수정·추가한 파일

- `agents/kr_intraday_slack/llm_client.py` (신규)
- `agents/kr_intraday_slack/ai_judge.py` (신규)
- `agents/kr_intraday_slack/pipeline.py` (LLM 필수 경로)
- `agents/kr_intraday_slack/slack_message.py` (`build_slack_message_from_ai`)
- `agents/kr_intraday_slack/send_filter.py` (`require_ai`)
- `agents/kr_intraday_slack/watchlist_pick.py` (후보 최대 7)
- `scripts/run_kr_intraday_slack.py` (AI 상태 출력, `--send` 가드)
- `agents/kr_intraday_slack/README.md`

### 환경변수 (하드코딩 없음)

```env
AI_PROVIDER=deepseek
AI_MODEL=deepseek-chat
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

`AI_MODEL` 미설정 시 `DEEPSEEK_MODEL` → 최종 fallback `deepseek-chat`.

### 파이프라인 흐름

1. `collect_watchlist_market_data` (dummy 또는 `--live`)
2. `pick_watchlist_candidates` 규칙 1차 (최대 7)
3. `run_ai_judgments` → DeepSeek JSON `{ "decisions": [...] }`
4. `send_slack=true` + 허용 decision 만 `build_slack_message_from_ai`
5. `filter_for_slack_send(require_ai=True)` 최대 3건

### 테스트 명령어

```powershell
# 드라이런 (더미 시세 + LLM, 슬랙 미발송)
python scripts/run_kr_intraday_slack.py --slot 0930

# 라이브 시세 + LLM 드라이런
python scripts/run_kr_intraday_slack.py --slot 0930 --live

# 실발송 (AI 승인 메시지 있을 때만)
python scripts/run_kr_intraday_slack.py --slot 0930 --live --send
```

### 성공/실패 조건

| 조건 | 동작 |
|------|------|
| `DEEPSEEK_API_KEY` 없음 | `ai_errors` 로그, 메시지 0, `--send` 해도 미발송 |
| LLM API 오류 | 동일, 더미 판단 **없음** |
| JSON 파싱 실패 | 동일 |
| `send_slack=false` / 금지 decision | 해당 종목 스킵, 로그 `skip_reason` |
| `send_slack=true` + 허용 decision | 메시지 생성 → `--send` 시 Slack |

### 실행 로그 예시 (2026-05-21, dummy + deepseek-chat)

```text
INFO kr_intraday.llm: [kr_intraday_batch] LLM OK provider=deepseek model=deepseek-chat
INFO kr_intraday.ai_judge: [KR INTRADAY AI] slot=0930 candidates=4 send_slack=4 errors=0
messages: 4 (드라이런, --send 없음)
```

### 실패 시 미발송 보장

- 규칙 기반 `evaluate_entry` / `build_slack_message` 는 슬랙 경로에서 **사용 안 함**
- `--send` 분기: `not result.messages` 또는 `not result.ai_enabled` → `send_kr_intraday_slack` 호출 안 함

### 다음 작업

- Actions에 `AI_PROVIDER` / `AI_MODEL` secrets 추가
- `deepseek-reasoner` vs `deepseek-chat` 운영 모델 선택 가이드
- LLM 배치 실패 시 종목별 재시도(선택)

## 2026-05-21 작업 기록 — 멀티 모델 optional (Grok/Gemini)

### 수정·추가한 파일

| 구분 | 파일 |
|------|------|
| 설정 | `agents/kr_intraday_slack/llm_client.py` (`primary`/`social`/`summary`, `aux_models_status`) |
| Grok 보조 | `agents/kr_intraday_slack/grok_social.py` (신규) |
| Gemini polish | `agents/kr_intraday_slack/gemini_polish.py` (신규) |
| 파이프라인 | `agents/kr_intraday_slack/pipeline.py`, `slack_message.py` |
| 실행 | `scripts/run_kr_intraday_slack.py` |
| 발송 로그 | `slack_sender.py` (`grok_context`, `gemini_polish` 필드) |
| 문서 | `agents/kr_intraday_slack/README.md`, `.env.example` |

### 환경변수 (추가)

```env
AI_SOCIAL_PROVIDER=grok
AI_SOCIAL_MODEL=grok-3
GROK_API_KEY=

AI_SUMMARY_PROVIDER=gemini
AI_SUMMARY_MODEL=gemini-1.5-flash
GEMINI_API_KEY=
```

### 파이프라인 흐름 (갱신)

1. 규칙 1차 후보 → **DeepSeek** `run_ai_judgments`
2. **Grok** `enrich_rows_with_grok` (`ai_send_slack=true` 만, optional)
3. SendFilter → `build_slack_message_from_ai` (Grok 맥락은 판단 섹션에 병합)
4. **Gemini** `polish_slack_message` (optional, 실패 시 초안)
5. `--send` 시 `send_kr_intraday_slack` (조건은 DeepSeek `ai_send_slack` 그대로)

### 테스트 명령어

```powershell
# DeepSeek만 (Grok/Gemini 키 없으면 skip 로그)
python scripts/run_kr_intraday_slack.py --slot 0930

# optional 모델 상태 확인
python scripts/run_kr_intraday_slack.py --slot 0930 --json

# 라이브 + 드라이런
python scripts/run_kr_intraday_slack.py --slot 0930 --live
```

### 성공/실패 조건

| 조건 | 동작 |
|------|------|
| `DEEPSEEK_API_KEY` 없음 | 메시지 0, 슬랙 미발송 (기존과 동일) |
| `GROK_API_KEY` 없음 | `grok_notes`에 skip, DeepSeek 단독 진행 |
| Grok API/JSON 실패 | 해당 종목 `grok_status=skipped`, 발송 조건 불변 |
| `GEMINI_API_KEY` 없음 | `gemini_polish.status=skipped`, DeepSeek 초안 사용 |
| Gemini 실패/금지표현/형식불일치 | `status=fallback`, 초안 사용 |
| Grok이 `send_slack` 변경 시도 | 코드상 병합만, `ai_send_slack` 미변경 |

### 로그 필드 (`data/logs/kr_slack/*.jsonl`)

- `grok_status`, `grok_skip_reason`, `grok_context`
- `gemini_polish`, `slack_message_draft`
- 스캔 요약: `aux_models` (primary/grok/gemini configured 여부)

### 다음 작업

- Gemini 모델명 정합 후 polish `status=ok` 검증 (위 E2E 검증 섹션 참고)

## 2026-05-21 작업 기록 — 실운영 수동 발송·슬랙 실전 톤

### 목표

- GitHub Actions **Run workflow** 로 장중 실스캔·실슬랙 발송
- 기본값: `--live --send` (SendFilter·DeepSeek `ai_send_slack` 조건 유지)
- 슬랙 본문에서 **테스트/드라이런/검증** 표현 제거, 실전용 라벨·말투

### 수정 파일

| 파일 | 내용 |
|------|------|
| `.github/workflows/kr_intraday_slack.yml` | `workflow_dispatch` inputs: slot/live/send/max_messages |
| `scripts/run_kr_intraday_slack.py` | `--max-messages`, `--dry-run`/`--send` 상호 배제, mode 로그 |
| `agents/kr_intraday_slack/constants.py` | 실전 decision 라벨, `DECISION_ALIASES`, `SLACK_BODY_FORBIDDEN` |
| `agents/kr_intraday_slack/message_tone.py` | `[진입 검토]` 등 표시, `1주 기준` 문구 |
| `agents/kr_intraday_slack/slack_message.py` | 금지어·라벨 검증 |
| `agents/kr_intraday_slack/entry_price.py`, `ai_judge.py`, `llm_client.py`, `gemini_polish.py`, `send_filter.py` | 라벨·alias 정합 |

### workflow_dispatch 사용법

1. GitHub → **Actions** → **KR Intraday Slack Scan** → **Run workflow**
2. Inputs (기본값이 실운영):
   - **slot**: `auto` (KST 시각→0930/1050/1350/1450) 또는 고정 슬롯
   - **live**: `true` (KIS/pykrx)
   - **send**: `true` (실슬랙; `false`면 드라이런만)
   - **max_messages**: `3`
3. Preflight `OK` 확인 후 스캔 로그·artifact(`scan.log`, `data/logs/kr_slack/*.jsonl`)

### 수동 발송 명령 (로컬·운영 동일)

```powershell
# 실운영 (live + Slack)
python scripts/run_kr_intraday_slack.py --slot auto --live --send

# 슬롯 고정
python scripts/run_kr_intraday_slack.py --slot 1050 --live --send --max-messages 3

# 드라이런 (메시지 생성만, Slack 미발송)
python scripts/run_kr_intraday_slack.py --slot 0930 --live --dry-run

# 더미 시세 + 미리보기
python scripts/run_kr_intraday_slack.py --slot 0930
```

### 자동 발송 시간 (KST, 월~금)

| KST | slot | cron (UTC) |
|-----|------|------------|
| 09:30 | 0930 | `30 0 * * 0-4` |
| 10:50 | 1050 | `50 1 * * 0-4` |
| 13:50 | 1350 | `50 4 * * 0-4` |
| 14:50 | 1450 | `50 5 * * 0-4` |

스케줄 실행은 항상 `--live --send --max-messages 3`.

### Slack 메시지 라벨 변경

| 이전 (슬랙 제목) | 이후 |
|------------------|------|
| 테스트 진입 검토 | **진입 검토** |
| 예약가 제안 | **예약가 후보** |
| 눌림 진입 가능 | **눌림 확인** |
| 관찰 강화 | 관찰 강화 (유지) |
| 수급 반전 감지 | 수급 반전 감지 (유지) |

본문: `1주 테스트` → **`1주 기준`** / `소액 기준` 권장.  
금지(본문): `테스트`, `드라이런`, `검증` — 로그의 `dry_run`/`mode=send`는 Slack에 노출 안 함.

### 실제 발송 조건 (변경 없음·요약)

1. `--send` (또는 Actions `send=true`)
2. DeepSeek `ai_send_slack=true`
3. `decision` ∈ {진입 검토, 관찰 강화, 눌림 확인, 예약가 후보, 수급 반전 감지} (구 라벨은 alias로 정규화)
4. `SendFilter`: 당일 중복·최대 `max_messages`건
5. 메시지 본문 생성 성공 + 금지 표현 없음
6. **0건이면 Slack API 호출 없음**

## 2026-05-21 작업 기록 — Slack 메시지 mrkdwn 가독성 개선 및 경고 표현 변경

### 변경 요약

- Slack 본문을 **mrkdwn** 구조로 재작성 (📌 제목, `*현재가*` / `*예약가 후보*` 굵은 라벨, `• *1주 기준*` / `• *경고*` bullet).
- **「취소 조건」→「경고」** (본문·Gemini polish·금지어 목록). JSON 필드명 `cancel_condition` 은 유지(내용만 경고 문장).
- 여러 종목 발송 시 **한 번의 postMessage** + 종목 사이 `――――――――――` 구분선 (`join_intraday_slack_messages`).

### 수정 파일

| 파일 | 내용 |
|------|------|
| `agents/kr_intraday_slack/message_tone.py` | mrkdwn `compose_slack_message`, `sanitize_slack_mrkdwn`, `join_intraday_slack_messages` |
| `agents/kr_intraday_slack/slack_message.py` | 발송 전 sanitize |
| `agents/kr_intraday_slack/gemini_polish.py` | mrkdwn 프롬프트, 취소 조건 치환, 실패 시 재조립 |
| `agents/kr_intraday_slack/ai_judge.py` | `cancel_condition` 프롬프트(경고 문장) |
| `agents/kr_intraday_slack/constants.py` | `취소 조건` 본문 금지, `SLACK_STOCK_SEPARATOR` |
| `slack_sender.py` | 다종목 합쳐 1회 발송 |

### 메시지 형식 (예)

```
📌 *[진입 검토] 심텍*

*현재가* 124,700원
*예약가 후보* 106,000원 ~ 110,000원

…판단 1~2문장…

• *1주 기준*
106,000원 ~ 110,000원 구간에서만 진입 검토

• *경고*
109,000원 이탈 또는 거래 급감 시 오늘은 넘기기
```

예약가 후보 없으면 `*예약가 후보* -` + 관찰/눌림 중심 문장.

## 2026-05-21 작업 기록 — Slack 메시지 섹터별 요약 구조 적용

### 변경 요약

- 종목별 메시지 이어 붙이기 → **섹터별 요약 1건** (`compose_sector_summary_message`).
- 관심 **5개 섹터 항상 표시** (종목 없으면 `진입 검토 종목 없음`).
- SendFilter 통과 종목만 섹터 카드에 표시 (`max_messages` 전체 상한 + **섹터당 최대 2종목**).
- Slack **postMessage 1회** (섹터 요약 본문).

### 수정 파일

| 파일 | 내용 |
|------|------|
| `agents/kr_intraday_slack/message_tone.py` | `group_rows_by_sector`, `compose_sector_stock_block`, `compose_sector_summary_message` |
| `agents/kr_intraday_slack/slack_message.py` | `build_sector_slack_summary` |
| `agents/kr_intraday_slack/pipeline.py` | 섹터 요약 1건 생성 → Gemini sector polish |
| `agents/kr_intraday_slack/gemini_polish.py` | `polish_sector_summary_message` (구조 유지) |
| `agents/kr_intraday_slack/send_filter.py` | `MAX_STOCKS_PER_SECTOR=2` |
| `agents/kr_intraday_slack/constants.py` | `MAX_STOCKS_PER_SECTOR` |
| `slack_sender.py` | 요약 메시지 1회 발송, 로그 `sector_summary` |

### 메시지 골격

```
📊 *장중 관심종목 스캔*
기준 슬롯 / 스캔 대상 25개
――――――――――
*{섹터명}*
진입 검토 종목 N개 | 없음
📌 *종목* + 현재가·예약가·판단·경고
(섹터 구분선 반복 ×5)
```

## 2026-05-21 작업 기록 — 섹터별 병렬 스캔 파이프라인

### 목표

- 관심 **5섹터** 기준 시세 수집·1차 후보 선별을 **병렬** 처리해 실행 시간 단축.
- DeepSeek은 섹터 결과 **merge 후 배치 1회**(최대 7종목) 유지.
- 섹터 1개 실패 시 전체 중단 없이 로그만 남기고 나머지 섹터 계속.

### 흐름

```text
run_sector_scan_parallel (5 workers)
  └─ scan_one_sector ×5
       ├─ collect_sector_market_data
       ├─ judge_single_sector_mood
       └─ pick_sector_candidates (섹터당 최대 2)
merge_sector_scan_results → candidates[:7]
run_ai_judgments (DeepSeek 1회)
enrich_rows_with_grok (ai_send_slack=true, 병렬 최대 3)
SendFilter → compose_sector_summary_message → Gemini polish 1회 → Slack 1회
```

### 추가·수정 파일

| 파일 | 내용 |
|------|------|
| `agents/kr_intraday_slack/sector_scan.py` | **신규** — `run_sector_scan_parallel`, `merge_sector_scan_results` |
| `agents/kr_intraday_slack/market_data.py` | `collect_sector_market_data` |
| `agents/kr_intraday_slack/watchlist_pick.py` | `pick_sector_candidates`, `_score_row` |
| `agents/kr_intraday_slack/sector_mood.py` | `judge_single_sector_mood` |
| `agents/kr_intraday_slack/grok_social.py` | Grok 병렬 enrich |
| `agents/kr_intraday_slack/pipeline.py` | 섹터 병렬 스캔 경로, `sector_scan_notes` |

### 유지 사항

- Slack: 5섹터 헤더 항상 표시, SendFilter·`max_messages`·실전 톤 동일.
- 발송 0건이면 postMessage 없음 (기존과 동일).

## 2026-05-21 작업 기록 — GitHub Actions closed stderr 수정

### 증상

- Actions 실행 말미: `ValueError: I/O operation on closed file` / `lost sys.stderr`
- KIS/pykrx·DeepSeek·Grok까지는 진행된 뒤 Gemini/종료 로그 단계에서 발생

### 원인

- **섹터 병렬 스캔** 시 `data/kr_market._suppress_pykrx_output()` 가 `contextlib.redirect_stdout/stderr` 로 전역 스트림을 교체
- 여러 스레드가 동시에 redirect/복구하면서 `stderr` 가 닫힌 devnull 파일을 가리키거나 복구가 깨짐
- 이후 `logging` / `print` / Gemini 경고 출력 시 실패 → exit code 1

### 수정

| 항목 | 내용 |
|------|------|
| `data/kr_market.py` | `_pykrx_io_lock` + redirect 종료 시 항상 `sys.__stdout__` / `sys.__stderr__` 복구 |
| `utils/safe_stdio.py` | **신규** — `ensure_stdio`, `setup_logging`(StreamHandler→`__stderr__`), `safe_print` |
| `scripts/run_kr_intraday_slack.py` | `basicConfig` 제거, safe print, scan 전후 `ensure_stdio` |
| `pipeline.py` / `sector_scan.py` / `gemini_polish.py` | 병렬 수집·Gemini 직전 `ensure_stdio()` |
| `.github/workflows/kr_intraday_slack.yml` | `tee scan.log` + `pipefail` + `PIPESTATUS[0]` 로 종료 코드 전달, `if: always()` artifact 유지 |

### CI 로그 저장

- Python 내부 redirect **사용 안 함**
- 셸: `python ... 2>&1 | tee scan.log` (실패 시에도 `scan.log` artifact 업로드)

## 2026-05-21 작업 기록 — Slack 진입 구간·경고 표현·줄임표 제거

### 배경

- Grok/이슈 문장이 68자 등에서 `…`로 잘려 의미가 끊김.
- "예약가 후보"·"경고"가 매수 가격으로 오해될 수 있음.
- 사용자 의도: **진입 후보 구간** = 1주 기준 매수 타이밍을 노릴 가격대, **경고** = 매수가 아닌 무효·오늘은 넘기기 기준.

### 변경 요약

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 가격대 라벨 | 예약가 후보 | **진입 후보 구간** |
| 종목 카드 | `현재가:` / 짧은 `…` 절단 | `*현재가*`, `*진입 후보 구간*`, 완성 문장 2~4개 |
| Grok | 67자 + `…` | `grok_issue_sentences` 완성 문장 최대 2개, 초과 시 생략 |
| 경고 | 짧게 잘림 가능 | 회피 기준 문장(이탈·거래 급감), 매수가 접두 제거 |
| 검증 | 없음 | `contains_slack_ellipsis`, `sanitize`·Gemini·`build_sector_slack_summary`에서 `...`/`…` 거부 |

### 수정 파일

| 파일 | 내용 |
|------|------|
| `agents/kr_intraday_slack/message_tone.py` | `_complete_sentences`, `_reject_ellipsis_body`, `compose_sector_stock_block` 포맷, 용어·서술 |
| `agents/kr_intraday_slack/slack_message.py` | 발송 전 줄임표 검사 |
| `agents/kr_intraday_slack/grok_social.py` | 완성 문장·줄임표 금지 프롬프트 |
| `agents/kr_intraday_slack/gemini_polish.py` | 진입 후보 구간/경고 의미, ellipsis 거부 |
| `agents/kr_intraday_slack/ai_judge.py` | reason/cancel_condition 톤 가이드 |

### Slack 예시 (심텍, 변경 후)

```text
📌 *심텍*

*현재가* 124,700원
*진입 후보 구간* 119,000원 ~ 122,000원

반도체 부품 쪽에서 다시 관심이 붙는 흐름입니다.
…(Grok 완성 문장 0~2개)…
다만 바로 따라가기보다는, 위 구간까지 눌리는지 보는 게 좋아 보입니다.

• *1주 기준*
119,000원 ~ 122,000원 구간에서만 진입 검토

• *경고*
109,000원 이탈 또는 거래 급감 시 오늘은 넘기기
```

로컬 `compose_sector_stock_block` / `build_sector_slack_summary` 기준 **`...`/`…` 없음** 확인.

### 변경 전 (참고)

```text
📌 *심텍*
현재가: 124,700원
예약가 후보: 119,000원 ~ 122,000원

반도체 부품 쪽에서 다시 관심이 붙는 흐름입니다.
이슈: 반도체 장비 수주 기대감이 다시 거론되면서 부품주로 관심이 확산되는 분…
다만 바로 따라가기보다 눌림 구간을 보는 쪽이 좋아 보입니다.
1주 기준이라면 예약가 후보 구간에서만 진입 검토.

• *경고*
109,000원 이탈 또는 거래 급감 시 오늘은 넘기기
```

## 2026-05-21 작업 기록 — Slack 섹터 요약 종목 노출 상한 명확화

### 규칙 (코드·문서 동기화)

| 상한 | 값 | 비고 |
|------|-----|------|
| 전체 상세 종목 | `max_messages` (기본 3) | SendFilter |
| 섹터당 상세 | 최대 2 | `MAX_STOCKS_PER_SECTOR` |
| 섹터당 1개 고정 | **없음** | 한 섹터에 2개 가능 (전체 상한 내) |
| 빈 섹터 | 「진입 검토 종목 없음」 | 5섹터 헤더 항상 표시 |

### 예 (`max_messages=3`)

- 반도체 부품 2 + 방산·우주 1
- 반도체 소재·부품·장비 각 1

### 구현

- `send_filter.py`: 모듈 docstring, `sort_rows_by_pick_score`, `select_within_send_limits`, `sort_send_rows_for_summary` — **점수 순 선정** 후 섹터 표시 순 정렬 (LLM 응답 순서에 덜 의존)
- `tests/test_send_filter.py`: 상한·정렬 단위 테스트
- `message_tone.py` / `slack_message.py` / `README.md` docstring 보강

## 2026-05-21 작업 기록 — 진입 후보 구간 `-` 표시 제거

### 증상

- AI `entry_price_range`가 85%~100% 검증에 걸려 규칙값으로 되돌렸으나, 파이프라인에 `evaluate_entry` 미적용으로 `entry_range`가 빈 문자열 → Slack `진입 후보 구간 -`.

### 수정

| 항목 | 내용 |
|------|------|
| AI 밴드 | 70%~102% 허용, `high > current` → current로 보정 |
| 너무 넓음 | `high-low > current×8%` → 95%~99%로 보정 |
| fallback | `entry_price.build_entry_range_fallback` — day_low/prev_close/support 우선, 없으면 95%~99% |
| 발송 | 구간 없으면 `ai_send_slack=false` + SendFilter 제외 |
| Slack | `compose_sector_stock_block` — 구간 없으면 카드 미생성, `-` 미사용 |
| 로그 | AI 사용 / AI 보정 / 규칙 fallback / 계산 불가 구분 |

### 동진쎄미켐 예시 (AI 단위 오류 `6150~61000`, current 61,500)

- `entry_range_source`: `rule_anchor` (day_low 59,800 반영)
- Slack:

```text
*진입 후보 구간* 59,700원 ~ 59,900원
• *경고*
57,000원 이탈 또는 거래 급감 시 오늘은 넘기기
```

### 파일

- `entry_price.py`, `ai_judge.py`, `message_tone.py`, `send_filter.py`, `tests/test_entry_range.py`

## 기록 규칙

Cursor는 각 작업 완료 후 위 형식으로 추가 기록한다.
