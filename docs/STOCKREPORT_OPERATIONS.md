# stockreport 운영 정리 (GitHub Actions · Slack · 환경변수)

최종 갱신: 2026-05-21

## 1. 실사용 Slack (2채널)

| Slack 채널 (권장 이름) | 기능 | 실행 | 환경변수 |
|------------------------|------|------|----------|
| **오늘 매수 후보 알림** | 장전 매수 후보 + 장후(내일 볼) 후보 스캔 | `morning_buy_alert.yml`, `tomorrow_watch_alert.yml` | `SLACK_BUY_CANDIDATE_CHANNEL` 또는 `SLACK_BUY_CANDIDATE_WEBHOOK` |
| **관심종목 새벽 리포트** | 관심 25종목 새벽 재판단·뉴스·수급·위험 | `watchlist_dawn_report.yml` | `SLACK_WATCHLIST_REPORT_CHANNEL` 또는 `SLACK_WATCHLIST_REPORT_WEBHOOK` |

- 두 기능은 **워크플로·스크립트·Slack 목적이 분리**되어 있으며, 파이프라인을 하나로 합치지 않습니다.
- 장후 후보(구 「내일 볼 종목」)는 **별도 Slack 채널을 만들지 않고** 매수 후보 채널로만 발송합니다.

### 환경변수

| 변수 | 기본값 | 의미 |
|------|--------|------|
| `DAILY_PICK_AUTO_SEND` | `true` | 장전·장후 매수 후보 Slack |
| `WATCHLIST_REVIEW_AUTO_SEND` | `false` (새벽 WF에서는 `true`) | 새벽 리포트 Slack |
| `WATCHLIST_AUTO_APPLY` | `false` | `kr_watchlist.json` 자동 반영 |
| `CANDIDATE_AUTO_REPLACE` | `false` | 후보→watchlist 자동 교체 |

레거시 `SLACK_CHANNEL_KR` 은 **매수 후보 채널 폴백**만 사용합니다 (신규 설정 권장).

---

## 2. GitHub Actions

### A. 오늘 매수 후보 알림 (장전)

- **파일**: `.github/workflows/morning_buy_alert.yml`
- **스케줄**: UTC `25 1 * * 1-5` → KST **10:25** (월~금)
- **스크립트**: `scripts/run_morning_buy_alert.py`

### B. 오늘 매수 후보 알림 · 장후 후보

- **파일**: `.github/workflows/tomorrow_watch_alert.yml`
- **스케줄**: UTC `55 6 * * 1-5` → KST **15:55**
- **스크립트**: `scripts/run_tomorrow_watch_alert.py`
- **Slack**: 매수 후보와 **동일 채널** (`post_buy_candidate_message`)

### C. 관심종목 새벽 리포트

- **파일**: `.github/workflows/watchlist_dawn_report.yml`
- **스케줄**: UTC `30 20 * * 0-4` → KST **05:30** (월~금)
- **스크립트**: `scripts/run_weekly_watchlist_update.py`
- **스케줄 시**: `--with-news`, `--send-slack`, `WATCHLIST_REVIEW_AUTO_SEND=true`

### 제거·정리됨

| 구 Actions/채널명 | 조치 |
|-------------------|------|
| HTML 디자인 테스트 | WF 이름 변경, **Slack env 제거** |
| KR Market Watchlist Verify | WF 이름 변경, **Slack 발송 없음** (기존과 동일) |
| 내일 볼 종목 알림 | WF → 「오늘 매수 후보 · 장후 후보」, 채널 통합 |
| 내일 볼 종목 알림 (수동 테스트) | `candidate_scan_test.yml` **삭제** |
| 관심종목 재평가 리포트 | → `watchlist_dawn_report.yml` 로 대체 |

---

## 3. 로컬 CLI (요약)

```bash
# 장전 매수 후보
python scripts/run_morning_buy_alert.py --live-data --send-slack

# 장후 후보 (동일 Slack 채널)
python scripts/run_tomorrow_watch_alert.py --live-data --send-slack

# 새벽 관심종목 리포트
WATCHLIST_REVIEW_AUTO_SEND=true python scripts/run_weekly_watchlist_update.py --with-news --send-slack
```

---

## 4. Secrets (GitHub)

필수: `DEEPSEEK_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_BUY_CANDIDATE_CHANNEL` (또는 WEBHOOK), `SLACK_WATCHLIST_REPORT_CHANNEL` (또는 WEBHOOK), `KIS_*`, `KRX_*`

선택: `GEMINI_API_KEY`, `GROK_API_KEY`, `DART_API_KEY`, `NAVER_*`

자세한 표: `.github/workflows/README.md`
