# GitHub Actions — Slack 발송 정책

## 자동 Slack 발송 (운영)

| Workflow | 용도 |
|----------|------|
| **kr_intraday_slack.yml** | 장중 관심종목 알림 (KST 09:30 / 10:50 / 13:50 / 14:50, `--live --send`) |

## 비활성화 (예전 리포트 브리핑)

| Workflow | 상태 |
|----------|------|
| 01_us_close.yml | DISABLED — `main.py us_close_kr_before` Slack 미운영 |
| 02_kr_open.yml | DISABLED — `main.py kr_during` Slack 미운영 |
| 03_kr_close.yml | DISABLED — `main.py kr_close_us_before` Slack 미운영 |
| 04_us_open.yml | DISABLED — `main.py us_during` Slack 미운영 |

## CI (Slack 없음)

| Workflow | 용도 |
|----------|------|
| kr_market_verify.yml | push/PR 시 kr_market 렌더 검증만 (Firebase 업로드, **Slack 미발송**) |
| test_html.yml | HTML 테스트 |

리포트 HTML/데이터 생성은 로컬 `main.py`로 가능. Slack은 `STOCKREPORT_ALLOW_LEGACY_REPORT_SLACK=1` 일 때만 예전 경로 허용.
