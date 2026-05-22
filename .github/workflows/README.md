# GitHub Actions

## 운영 (Slack·자동화)

| 파일 | Workflow (Actions 탭 이름) | 용도 |
|------|---------------------------|------|
| **daily_pick_alert.yml** | 매일 투자 후보 알림 | KST **10:30** / **13:50** 자동 + 수동. 오늘 볼 만한 종목 Slack |
| **watchlist_review.yml** | 관심종목 재평가 리포트 | **수동만**. 25종목 유지/주의/제외, proposal·리포트 |
| **candidate_scan_test.yml** | 신규 후보 스캔 테스트 | **수동만**. 신규 후보 탐색·JSON 제안 (watchlist 미수정) |

레거시 파일명 (삭제됨): `kr_intraday_slack.yml`, `weekly_watchlist.yml` → 위 3개로 대체.

전체 운영 설명: [docs/STOCKREPORT_OPERATIONS.md](../../docs/STOCKREPORT_OPERATIONS.md)

## CI / 검증 (Slack 발송 없음)

| 파일 | Workflow | 용도 |
|------|----------|------|
| kr_market_verify.yml | KR Market Watchlist Verify | push/PR 시 kr_market 렌더·Firebase 검증 |
| test_html.yml | HTML 디자인 테스트 | 템플릿 HTML 검증 |

## 삭제됨 (2026-05-21)

예전 장시작/장마감 브리핑 자동 발송 workflow:

- `01_us_close.yml`, `02_kr_open.yml`, `03_kr_close.yml`, `04_us_open.yml`

리포트 생성은 로컬 `main.py` 가능.

## Secrets 설정

GitHub → **Settings → Secrets and variables → Actions → Repository secrets**

| 이름 | 필수 | 용도 |
|------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | 1차 판단 |
| `SLACK_BOT_TOKEN` | ✅ | 슬랙 발송 |
| `SLACK_CHANNEL_KR` | ✅ | KR 채널 ID |
| `KIS_APP_KEY` | ✅ | 라이브 시세 |
| `KIS_APP_SECRET` | ✅ | 라이브 시세 |
| `GROK_API_KEY` | optional | X/뉴스 보조 |
| `GEMINI_API_KEY` | optional | 문장 polish |
| `DART_API_KEY` | optional | 주간 공시 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | optional | 주간 뉴스 |
| `KIS_ACCOUNT_NO` | optional | KIS |
| `KRX_ID` / `KRX_PW` | optional | pykrx |

### Variables (optional)

`AI_PROVIDER`, `AI_MODEL`, `AI_SOCIAL_*`, `AI_SUMMARY_*` — `daily_pick_alert.yml` job `env` 기본값 참고.

### Environment secrets

Secrets를 **Environment**에만 넣었다면 `daily_pick_alert.yml` 의 `jobs.daily_pick` 에 `environment: production` 등 추가.

## Run workflow 입력 (요약)

### 매일 투자 후보 알림

| 입력 | 기본값 |
|------|--------|
| 실행 기준 (`run_timing`) | 자동 |
| 실제 데이터로 확인 | true |
| Slack으로 보내기 | true |
| 최대 발송 개수 | 3 |

### 관심종목 재평가 리포트

| 입력 | 기본값 |
|------|--------|
| 실제 데이터로 확인 | true |
| 뉴스/공시 포함 | false |
| Slack으로 보내기 | false |
| 관심종목 자동 수정 | false |

### 신규 후보 스캔 테스트

| 입력 | 기본값 |
|------|--------|
| 스캔 종목 수 | 30 |
| 최근 며칠 흐름 | 5 |
| Slack으로 보내기 | false |
| 실제 데이터로 확인 | true |

로컬 동일 실행:

```bash
python scripts/run_kr_intraday_slack.py --slot auto --live --send --max-messages 3
python scripts/run_weekly_watchlist_update.py --no-llm --no-send
python scripts/run_candidate_scan_test.py --live-data --scan-count 30 --trend-days 5
```
