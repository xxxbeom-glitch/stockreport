# GitHub Actions

## 운영 Slack (2채널 · 3워크플로 — 실행 로직은 분리)

| 파일 | Actions 표시명 | 스케줄 (KST) | Slack 목적 |
|------|----------------|--------------|------------|
| **morning_buy_alert.yml** | 오늘 매수 후보 알림 | 평일 **10:25** | `SLACK_BUY_CANDIDATE_*` |
| **tomorrow_watch_alert.yml** | 오늘 매수 후보 알림 · 장후 후보 | 평일 **15:55** | 동일 (장후 후보 스캔) |
| **watchlist_dawn_report.yml** | 관심종목 새벽 리포트 | 평일 **05:30** | `SLACK_WATCHLIST_REPORT_*` |

- 매수 후보(장전·장후)는 **같은 Slack 채널**, 파이프라인·스케줄은 **별도 유지**
- 관심종목 새벽 리포트는 **독립 실행** (매수 후보와 합치지 않음)

상세: [docs/STOCKREPORT_OPERATIONS.md](../../docs/STOCKREPORT_OPERATIONS.md)

## CI (Slack 없음)

| 파일 | Actions 표시명 |
|------|----------------|
| **kr_market_verify.yml** | KR 관심종목 HTML 검증 (Slack 없음) |
| **test_html.yml** | HTML 템플릿 검증 (Slack 없음) |

## Secrets

**공통:** `DEEPSEEK_API_KEY`, `SLACK_BOT_TOKEN`, `KIS_APP_KEY`, `KIS_APP_SECRET`, `KRX_ID`, `KRX_PW`

**매수 후보 알림** (`morning_buy_alert`, `tomorrow_watch_alert`):

- `SLACK_BUY_CANDIDATE_CHANNEL` (채널 ID, Bot API·쓰레드 권장) **또는**
- `SLACK_BUY_CANDIDATE_WEBHOOK` (Incoming Webhook, 단일 메시지)
- 마이그레이션: `SLACK_CHANNEL_KR` 이 있으면 매수 후보 채널로 폴백

**관심종목 새벽 리포트** (`watchlist_dawn_report`):

- `SLACK_WATCHLIST_REPORT_CHANNEL` **또는** `SLACK_WATCHLIST_REPORT_WEBHOOK`

**선택:** `GEMINI_API_KEY`, `GROK_API_KEY`, `DART_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
