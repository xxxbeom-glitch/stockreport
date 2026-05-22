# stockreport 운영 정리 (GitHub Actions · 실행 옵션 · Slack)

최종 갱신: 2026-05-21

## 1. 기능 분리 요약

| 기능 | Workflow (한글 이름) | 파일 | 스케줄 | Slack | watchlist 수정 |
|------|----------------------|------|--------|-------|----------------|
| **매일 투자 후보 알림** | 매일 투자 후보 알림 | `daily_pick_alert.yml` | KST 10:30·13:50 (월~금) | 기본 발송 (`DAILY_PICK_AUTO_SEND=true`) | 없음 |
| **관심종목 재평가** | 관심종목 재평가 리포트 | `watchlist_review.yml` | 없음 (수동만) | 기본 꺼짐 (`WATCHLIST_REVIEW_AUTO_SEND=false`) | 기본 꺼짐 (`WATCHLIST_AUTO_APPLY=false`) |
| **신규 후보 스캔 테스트** | 신규 후보 스캔 테스트 | `candidate_scan_test.yml` | 없음 | 기본 꺼짐 (수동 `--send-slack`만) | 없음 (제안 JSON만) |

두 기능(매일 후보 vs 관심종목 재평가)은 **워크플로·스크립트·Slack 게이트·환경변수**가 분리되어 있으며, 하나로 묶지 않습니다.

### 환경변수 (GitHub Actions `env` / 로컬)

| 변수 | 기본값 | 의미 |
|------|--------|------|
| `DAILY_PICK_AUTO_SEND` | `true` | 장중 매일 투자 후보 Slack (스케줄·`--send`) |
| `WATCHLIST_REVIEW_AUTO_SEND` | `false` | 주간 재평가 Slack 자동 발송 |
| `WATCHLIST_AUTO_APPLY` | `false` | `kr_watchlist.json` 자동 반영 |
| `CANDIDATE_AUTO_REPLACE` | `false` | 후보→watchlist 자동 교체 |
| `SAFE_MODE` | (미설정) | 레거시 — **장중 발송에는 미사용**, 주간 자동화 제한용 |

로그 배너 (`utils/safe_mode.py`):

- `[DAILY_PICK] Slack 발송 가능`
- `[WATCHLIST_REVIEW] 자동 발송 중지` / `자동 수정 중지`
- `[CANDIDATES] 제안만 생성` / `자동 교체 중지`

---

## 2. GitHub Actions

### A. 매일 투자 후보 알림

- **이름**: `매일 투자 후보 알림`
- **파일**: `.github/workflows/daily_pick_alert.yml`
- **목적**: 관심종목 25개 중 오늘 볼 만한 종목을 스캔해 Slack 발송
- **스케줄**: UTC `30 1 * * 0-4` (KST 10:30), `50 4 * * 0-4` (KST 13:50)
- **실행 스크립트**: `scripts/run_kr_intraday_slack.py`

#### Run workflow 입력

| 입력 ID | 화면 설명 | 기본값 | 내부 매핑 |
|---------|-----------|--------|-----------|
| `run_timing` | 실행 기준 (자동 / 장전 / 장중 / 장마감) | `auto` | → `--slot` 1030 또는 1350 |
| `use_live_data` | 실제 데이터로 확인 | `true` | → `--live` |
| `send_slack` | Slack으로 보내기 | `true` | → `--send` / 미체크 시 `--dry-run` |
| `max_pick_count` | 최대 발송 개수 | `3` | → `--max-messages` |

`SAFE_MODE`, `SLACK_AUTO_SEND` 등은 **Run workflow 화면에 노출하지 않음** (job `env`만 설정).

### B. 관심종목 재평가 리포트

- **이름**: `관심종목 재평가 리포트`
- **파일**: `.github/workflows/watchlist_review.yml`
- **목적**: 기존 25종목 유지/주의/제외 판단, proposal·리포트 생성
- **스케줄**: 없음 (`# schedule:` 주석 — 자동 재구성 중지)
- **실행 스크립트**: `scripts/run_weekly_watchlist_update.py`

#### Run workflow 입력

| 입력 ID | 화면 설명 | 기본값 |
|---------|-----------|--------|
| `use_live_data` | 실제 데이터로 확인 | `true` (false → `--pykrx-only`) |
| `include_news` | 뉴스/공시 포함 | `false` (`--with-news`) |
| `send_slack` | Slack으로 보내기 | `false` (`--send-slack` / `WATCHLIST_REVIEW_AUTO_SEND=true` 필요) |
| `apply_watchlist` | 관심종목 자동 수정 | `false` (체크해도 `WATCHLIST_AUTO_APPLY` 없으면 미반영) |

### C. 신규 후보 스캔 테스트

- **이름**: `신규 후보 스캔 테스트`
- **파일**: `.github/workflows/candidate_scan_test.yml`
- **목적**: watchlist 제외 유니버스에서 신규 후보 탐색·검증
- **실행 스크립트**: `scripts/run_candidate_scan_test.py`

#### Run workflow 입력

| 입력 ID | 화면 설명 | 기본값 |
|---------|-----------|--------|
| `scan_count` | 스캔 종목 수 | `30` |
| `trend_days` | 최근 며칠 흐름 | `5` |
| `send_slack` | Slack으로 보내기 | `false` |
| `use_live_data` | 실제 데이터로 확인 | `true` (`--live-data`) |

출력: `data/proposals/candidate_scan/`, `data/daily_scan/YYYY-MM-DD.json` — **watchlist 자동 수정 없음**.

---

## 3. 로컬 CLI (요약)

### 매일 투자 후보

```bash
python scripts/run_kr_intraday_slack.py --slot 1030 --live --send --max-messages 3
python scripts/run_kr_intraday_slack.py --slot auto --live --dry-run
```

### 관심종목 재평가

```bash
python scripts/run_weekly_watchlist_update.py --no-llm --no-send
python scripts/run_weekly_watchlist_update.py --no-llm --send-slack   # WATCHLIST_REVIEW_AUTO_SEND=true 필요
python scripts/run_weekly_watchlist_update.py --apply-watchlist        # WATCHLIST_AUTO_APPLY=true 필요
```

후보 스캔은 주간 스크립트의 `--with-candidates` 대신 **전용 테스트 스크립트** 권장:

```bash
python scripts/run_candidate_scan_test.py --live-data --scan-count 30 --trend-days 5
python scripts/run_candidate_scan_test.py --live-data --send-slack
```

---

## 4. Slack 메시지 구조

### 4.1 매일 투자 후보 (장중)

- **빌더**: `agents/kr_intraday_slack/slack_message.py` → `compose_new_candidate_scan_message`
- **제목 톤**: `📡 오늘 새로 볼 종목`
- **구조**:
  - 헤더: 기준 시각, 후보 개수
  - `🟢 지금 볼만함` — 발송 대상 (`SendFilter` 통과, decision ∈ 진입 검토·관찰 강화·눌림 확인·예약가 후보·수급 반전 감지)
  - `🟡 눌림·관찰` — 관찰 강화 계열
  - `🔴 오늘은 패스` — 최대 1종목 수준 (`select_pass_today_rows`)
- **종목 블록**: 이름, 현재가, 볼 구간, 이유, 체크 줄, 주의 (쉬운 말 scrub)
- **발송 게이트**: `can_send_daily_pick_slack(explicit_cli=--send, scheduled=--scheduled)` + `DAILY_PICK_AUTO_SEND`
- **후보 0건**: `--send` 시 안내 메시지 1건 발송 (제목에 장전/장중·시각 포함)
- **로그**: `data/logs/kr_slack/*.jsonl`

### 4.2 신규 후보 스캔 (테스트/주간 `--with-candidates`)

- **빌더**: `agents/weekly_watchlist_update/candidate_report.py` → `build_candidate_slack_text`
- **제목**: 동일 `📡 오늘 새로 볼 종목` (신규 후보만, watchlist 제외 유니버스)
- **푸터**: `_제안만 생성·watchlist 자동 수정 없음_`
- **등급**: `slack_green` / `slack_yellow` / pass(🔴) — 5 에이전트 투표 + `trend_score`(daily_scan 5일)
- **발송**: 후보 테스트는 `can_send_candidate_slack` (수동 `--send-slack`만)

### 4.3 관심종목 재평가 (주간)

- **빌더**: `agents/weekly_watchlist_update/weekly_report.py` (MD + Slack 요약)
- **뉴스 연동**: `news_context.py` (`--with-news` 시)
- **판단**: 유지 / 주의 / 제외 + proposal `data/proposals/watchlist_review/`
- **발송**: `can_send_watchlist_review_slack` — 기본 **중지**

---

## 5. 구현 현황 (MVP 기준)

| 영역 | 상태 | 비고 |
|------|------|------|
| MVP 1 주간 재평가 | ✅ | 25종목 metrics, sector mood, rule/LLM review |
| MVP 2 장중 Slack | ✅ | 1030/1350, SendFilter, entry range, thread bundle |
| MVP 3 뉴스/공시 | ✅ | 네이버·DART, `news_context`, 주간 리포트 반영 |
| MVP 4 후보 스캔 | ✅ | 5 agents, universe, scanner, daily_scan trend |
| MVP 4-3 trend_score | ✅ | `data/daily_scan/` 5일 누적 |
| 기능 분리 플래그 | ✅ | DAILY_PICK vs WATCHLIST_REVIEW |
| SAFE_MODE 잠정 중지 | ✅ | watchlist 자동 apply·주간 cron·자동 Slack |
| GitHub Actions 한글화 | ✅ | 3 workflow 분리 |
| 신규 후보 전용 workflow | ✅ | `candidate_scan_test.yml` |
| watchlist 자동 수정 | ⛔ | proposal만, env+CLI 이중 게이트 |
| 후보→watchlist 자동 교체 | ⛔ | `CANDIDATE_AUTO_REPLACE=false` |
| 레거시 US/KR open/close Slack | 제거됨 | `main.py` 리포트만 로컬 가능 |

---

## 6. CI (Slack 없음)

| 파일 | 용도 |
|------|------|
| `kr_market_verify.yml` | kr_market 렌더·Firebase 검증 |
| `test_html.yml` | HTML 템플릿 검증 |

---

## 7. Secrets (매일 투자 후보·재평가 공통)

필수: `DEEPSEEK_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_KR`, `KIS_APP_KEY`, `KIS_APP_SECRET`  
선택: `GROK_API_KEY`, `GEMINI_API_KEY`, `DART_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `KRX_ID`, `KRX_PW`

자세한 설정 절차: `.github/workflows/README.md`
