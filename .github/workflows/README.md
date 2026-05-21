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

## `KR Intraday Slack Scan` — Secrets 설정

### Repository secrets (권장)

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
| `KIS_ACCOUNT_NO` | optional | KIS |
| `KRX_ID` / `KRX_PW` | optional | pykrx |

### Variables (optional, 비밀 아님)

**Actions → Variables → Repository variables**

`AI_PROVIDER`, `AI_MODEL`, `AI_SOCIAL_PROVIDER`, `AI_SOCIAL_MODEL`, `AI_SUMMARY_PROVIDER`, `AI_SUMMARY_MODEL` — 미설정 시 workflow 기본값 사용.

### Environment secrets 사용 시

Secrets를 **Environment**(예: `production`)에만 넣었다면:

1. Settings → **Environments** 에서 environment 이름 확인
2. `kr_intraday_slack.yml` 의 `jobs.scan` 에서 주석 해제:
   ```yaml
   environment: production   # 실제 이름으로 변경
   ```
3. 해당 Environment에 위 표와 **동일한 secret 이름** 등록

Preflight 단계는 **job `env`에서 secrets를 받음** — step에만 env를 두면 MISSING이 난다 (2026-05-21 수정).

### 수동 검증

Actions → **KR Intraday Slack Scan** → **Run workflow** → Preflight 로그에 `OK DEEPSEEK_API_KEY` 등 표시 확인.
