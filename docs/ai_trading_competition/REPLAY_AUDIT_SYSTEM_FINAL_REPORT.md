# REPLAY / AUDIT 시스템 최종 리포트

**작성일:** 2026-05-24  
**기준 commit:** (push 후 갱신)  
**판정:** **REPLAY smoke 실행 완료 / Short·Month 경로 구현 / LIVE는 아직 중지**

---

## A. 최종 판정

**REPLAY smoke 실행 완료 / Short·Month·Full_audit 실행 경로 구현 / LIVE는 아직 중지**

- LIVE 자동 `schedule` cron 비활성화 유지
- REPLAY 전용 Firestore 컬렉션 분리 (`competition_replay_*`) — LIVE 계좌 컬렉션 미접근
- HTML LIVE/REPLAY 분리 + 주간·월간 REPLAY 리포트 + URL 쿼리 (`?mode=replay&report=...`)
- Slack: smoke 요약 금지, 주간·월간 리포트 링크만 (선택 `send_slack_reports`)
- **체결 검증 smoke:** `replay_20241218_16b6f721` — 20241218 판단 → 20241219 `pykrx_open_by_ticker` 체결 3건, leakage PASS

**LIVE 자동운용 시작 금지** — full replay 검증 및 `COMPETITION_ALLOW_LIVE_SESSION=1` 전까지.

---

## B. 실제 변경 파일 목록

| 파일 | 구분 |
|------|------|
| `src/trading/competition/replay/firestore_store.py` | 신규 — REPLAY Firestore sync/load |
| `src/trading/competition/replay/campaign.py` | 신규 — short_5days/month/full_audit |
| `src/trading/competition/replay/calendar.py` | 신규 — 거래일 해석 |
| `src/trading/competition/replay/reports.py` | 신규 — REPLAY 주간·월간 리포트 |
| `src/trading/competition/replay/slack_reports.py` | 신규 — 링크 전용 Slack |
| `src/trading/competition/replay/market_data.py` | 수정 — `get_market_ohlcv_by_date` per ticker |
| `src/trading/competition/replay/runner.py` | 수정 — single_day, Firestore sync, Slack 제거 |
| `src/trading/competition/dashboard/replay_payload.py` | 신규/수정 — Firestore 우선 읽기 |
| `scripts/run_competition_replay.py` | 수정 — `--replay-type`, campaign |
| `scripts/serve_mock_trading.py` | 수정 — REPLAY API |
| `template/dashboard_desktop/index.html` | 수정 — LIVE/REPLAY, 주간·월간, URL |
| `.github/workflows/competition_replay_audit.yml` | 수정 — replay types, `send_slack_reports` |
| `tests/competition/test_replay_campaign_slack.py` | 신규 |

---

## C. REPLAY Firebase 저장

| 컬렉션 | 용도 |
|--------|------|
| `competition_replay_runs/{replay_run_id}` | manifest + `dashboard_payload` |
| `competition_replay_campaigns/{campaign_id}` | multi-day campaign manifest |
| `competition_replay_weekly_reports/{report_id}` | 주간 리포트 |
| `competition_replay_monthly_reports/{report_id}` | 월간 리포트 |

- LIVE `competition_accounts` 등 **미쓰기**
- 로컬: `data/competition/replay/` + `campaigns/{id}/reports/`
- 로컬 검증: Firebase credentials 없음 → `firestore_ok: false`, `local_mirror` (CI secrets 있으면 Firestore 저장)

---

## D. 대시보드 · URL

- LIVE: `GET /api/trading-competition/dashboard`
- REPLAY: `GET /api/trading-competition/replay/dashboard?replay_run_id=...&campaign=...`
- 주간: `?mode=replay&campaign={id}&report=w51&reportType=weekly`
- 월간: `?mode=replay&campaign={id}&report=m202412&reportType=monthly`
- HTML은 API 경유로 Firestore(가능 시) 또는 로컬 REPLAY 파일 읽기

---

## E. Smoke 체결 검증 (20241218)

**run_id:** `replay_20241218_16b6f721`

| 항목 | 결과 |
|------|------|
| decision_at | 2024-12-18T15:30:00+09:00 |
| fill_date | 20241219 |
| leakage_summary | PASS |
| 체결 | B/C 대한전선 5주@11,430원, D 루닛 5주@34,311원 |
| fill_price_source | pykrx_open_by_ticker |
| LIVE 변경 | 없음 |

**Short campaign:** `short_5days_20241210_20241216_8b2e0d` — weekly w50/w51, monthly m202412 생성 확인

---

## F. Slack 정책

| 허용 | 금지 |
|------|------|
| 주간 리포트 링크 1건/주 | smoke 요약, 개별 매수·매도 |
| 월간 리포트 링크 1건/월 | replay 진행 상태 |
| 치명적 실패 (`send_fatal_replay_error`) | |

`COMPETITION_SLACK_WEBHOOK` ← `SLACK_WEBHOOK_TRADING`

---

## G. 테스트

`python -m unittest tests.competition.test_replay_campaign_slack tests.competition.test_replay_dashboard_payload tests.competition.test_replay_audit_system tests.competition.test_workflow_safety`

- **통과:** 33+ (replay 집중 스위트)

---

## H. 사용자 Actions

1. **체결 smoke:** `AI 투자 경쟁 리플레이 검증` → `smoke_1day`, `start_date=20241218`, `use_mock_llm` optional
2. **Short:** `replay_type=short_5days`, `start_date=20241210`, `send_slack_reports=true` (리포트 링크)
3. **대시보드:** `python scripts/serve_mock_trading.py` → `/template/dashboard_desktop/?mode=replay&replay_run_id=replay_20241218_16b6f721`

---

## I. LIVE schedule 복구

1. `competition_auto_ops.yml` schedule 주석 해제  
2. `COMPETITION_LIVE_SCHEDULE_DISABLED=0`  
3. replay short/month 검증 후 `COMPETITION_ALLOW_LIVE_SESSION=1`
