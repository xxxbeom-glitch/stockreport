# GitHub Actions

## 운영 (Slack 자동 — 평일 2회)

| 파일 | 이름 | 스케줄 (KST) | UTC cron |
|------|------|--------------|----------|
| **tomorrow_watch_alert.yml** | 내일 볼 종목 알림 | 평일 **15:55** → 16:00 전후 Slack | `55 6 * * 1-5` |
| **morning_buy_alert.yml** | 오늘 매수 후보 알림 | 평일 **10:25** → 10:30 전후 Slack | `25 1 * * 1-5` |

- 월~금: cron `1-5` (일요=0, 월=1 … 금=5)
- **13:50 자동 알림 제거됨** (레거시 `daily_pick_alert.yml` 삭제)

## 수동 전용

| 파일 | 이름 |
|------|------|
| **watchlist_review.yml** | 관심종목 재평가 리포트 |
| **candidate_scan_test.yml** | 내일 볼 종목 dry-run (`run_tomorrow_watch_alert.py`) |

상세: [docs/STOCKREPORT_OPERATIONS.md](../../docs/STOCKREPORT_OPERATIONS.md)

## Secrets

`DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `GROK_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_KR`, `KIS_APP_KEY`, `KIS_APP_SECRET`, `KRX_ID`, `KRX_PW`
