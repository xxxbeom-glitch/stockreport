# GitHub Actions

## 운영 (Slack 자동 발송)

| 파일 | Workflow | 용도 |
|------|----------|------|
| **kr_intraday_slack.yml** | KR Intraday Slack Scan | 장중 관심종목 알림 (KST 09:30/10:50/13:50/14:50, `--live --send`) |

## CI / 검증 (Slack 발송 없음)

| 파일 | Workflow | 용도 |
|------|----------|------|
| kr_market_verify.yml | KR Market Watchlist Verify | push/PR 시 kr_market 렌더·Firebase 검증 |
| test_html.yml | HTML 디자인 테스트 | 템플릿 HTML 검증 |

## 삭제됨 (2026-05-21)

예전 장시작/장마감 브리핑 자동 발송 workflow — repo에서 제거:

- `01_us_close.yml`, `02_kr_open.yml`, `03_kr_close.yml`, `04_us_open.yml`

리포트 생성은 로컬 `main.py` 가능. Slack 자동 발송은 `kr_intraday_slack.yml` 만 사용.
