# REPLAY / AUDIT 시스템 최종 리포트

**작성일:** 2026-05-24 (갱신)  
**기준 commit:** `ba1683f` + 로컬 미커밋(full_audit 종료·최종 리포트 모듈)  
**판정:** **REPLAY 경로·대시보드·리포트·종료 처리 구현 완료 / 2026-01~04 full_audit 실제 완주는 미실행 / LIVE 중지 유지**

---

## A. 최종 판정

| 영역 | 상태 |
|------|------|
| REPLAY smoke (단일 거래일) | ✅ 실행·체결 검증 완료 |
| Short / Month campaign | ✅ 구현·로컬 검증 |
| Full audit (2026-01~04) | ✅ **실행 경로·종료·최종 리포트** 구현 / ⏳ **전 기간 실제 완주 미실행** |
| LIVE 자동 운용 | 🛑 **중지** (`competition_auto_ops.yml` — 안내만) |
| 대시보드 LIVE/REPLAY | ✅ 분리·주간·월간·**최종** 리포트 UI |
| Slack | ✅ 주간·월간·**최종** 링크만 (개별 거래·smoke 요약 금지) |
| Firebase REPLAY | ✅ `competition_replay_*` 분리 (LIVE 계좌 미쓰기) |

**LIVE 자동운용 재개 금지** — `full_audit` REPLAY가 4월 말 거래일까지 완주·최종 리포트 PASS·`COMPETITION_ALLOW_LIVE_SESSION=1` 설정 전까지.

---

## B. REPLAY 유형 및 기간

| `replay_type` | 기간 | 비고 |
|---------------|------|------|
| `smoke_1day` | `--date` 1일 | 단일 run, Slack 없음 |
| `short_5days` | start~end 또는 start부터 5거래일 | 주간 리포트 생성 |
| `month` | 해당 월 1일~말일 | 월간 리포트 생성 |
| `full_audit` | **고정 `20260101`~`20260430`** | 입력 `--date`/`--end-date` **무시** |
| `custom` | start~end | 임의 구간 |

- 거래일: `calendar.list_trading_dates` (pykrx KOSPI 세션 확인)
- 개발 제한: `REPLAY_MAX_DAYS=N` → 앞에서 N거래일만 처리 (**full_audit 종료·최종 리포트·Slack 최종 미발송**)

---

## C. 구현 파일 목록

### REPLAY 코어 (`src/trading/competition/replay/`)

| 파일 | 역할 |
|------|------|
| `runner.py` | 단일 거래일 REPLAY, 익일 시가 체결, campaign 종료 후 판단 차단 |
| `campaign.py` | multi-day 오케스트레이션, full_audit 종료·최종 리포트·Slack |
| `calendar.py` | 거래일 해석 (`full_audit` → 고정 기간) |
| `period.py` | `FULL_AUDIT_START/END`, `is_full_audit_complete()` |
| `finalize.py` | 종료 시 mark-to-market (강제 매도 없음) |
| `final_report.py` | REPLAY 최종 종합 리포트 생성·저장 |
| `benchmark.py` | KOSPI/KOSDAQ 60/40 가중 벤치마크 (pykrx) |
| `reports.py` | 주간·월간 REPLAY 리포트, `load_campaign_reports` |
| `slack_reports.py` | 주간·월간·**최종** 링크, 치명 오류만 |
| `firestore_store.py` | REPLAY Firestore sync/load, 리포트 URL |
| `market_data.py` | pykrx per-ticker OHLCV, 익일 시가/종가 |
| `snapshot_builder.py` | 종가 스냅샷 |
| `leakage_audit.py` | 미래 데이터 침범 검사 |
| `code_auditor.py` | 규칙·계좌 검증 |
| `store.py` | run별 로컬 JSON/JSONL |

### 기타

| 파일 | 역할 |
|------|------|
| `dashboard/replay_payload.py` | REPLAY 대시보드 API payload (Firestore 우선) |
| `scripts/run_competition_replay.py` | CLI `--replay-type`, campaign 호출 |
| `scripts/serve_mock_trading.py` | `/api/trading-competition/replay/*` |
| `template/dashboard_desktop/index.html` | LIVE/REPLAY, 주간·월간·**최종 결과** |
| `.github/workflows/competition_replay_audit.yml` | Actions REPLAY 검증 |
| `.github/workflows/competition_auto_ops.yml` | LIVE 중지 (안내 job만) |

### 테스트

| 파일 | 내용 |
|------|------|
| `test_replay_audit_system.py` | smoke·침범·격리 |
| `test_replay_dashboard_payload.py` | payload·API |
| `test_replay_campaign_slack.py` | Slack 정책·캘린더 |
| `test_replay_final_report.py` | 종료·최종 리포트·Slack 최종 |
| `test_workflow_safety.py` | LIVE workflow 중지 검증 |

---

## D. 데이터 저장 구조

### 로컬 (LIVE와 분리)

```
data/competition/replay/
  {replay_run_id}/
    manifest.json
    snapshot.json
    decisions.jsonl
    trades.jsonl
    audit/
  campaigns/{campaign_id}/
    manifest.json          # competition_status, final_accounts 등
    final_accounts.json    # 종료 평가 스냅샷
    reports/
      weekly_{wNN}.json
      monthly_{mYYYYMM}.json
      final.json             # 최종 종합 리포트
      index.json
```

- LIVE `data/competition/` (accounts, positions 등) — REPLAY runner가 **쓰지 않음**

### Firestore (REPLAY 전용)

| 컬렉션 | 용도 |
|--------|------|
| `competition_replay_runs/{replay_run_id}` | manifest + `dashboard_payload` |
| `competition_replay_campaigns/{campaign_id}` | campaign manifest |
| `competition_replay_weekly_reports/{report_id}` | 주간 |
| `competition_replay_monthly_reports/{report_id}` | 월간 |
| `competition_replay_final_reports/{report_id}` | **최종 종합** |

- LIVE `competition_accounts`, `competition_positions` 등 **미접근**
- 로컬 credentials 없으면 `firestore_ok: false`, 로컬 파일만 사용

---

## E. 대시보드 · API · URL

### API

| 메서드 | 경로 |
|--------|------|
| GET | `/api/trading-competition/dashboard` — LIVE |
| GET | `/api/trading-competition/replay/runs` — REPLAY run 목록 |
| GET | `/api/trading-competition/replay/dashboard?replay_run_id=...&campaign=...` |
| GET | `/api/trading-competition/replay/campaigns` |

### URL 쿼리 (HTML)

| 용도 | 예시 |
|------|------|
| REPLAY 모드 | `?mode=replay&replay_run_id=replay_20241218_16b6f721` |
| 주간 | `?mode=replay&campaign={id}&report=w51&reportType=weekly` |
| 월간 | `?mode=replay&campaign={id}&report=m202412&reportType=monthly` |
| **최종** | `?mode=replay&campaign={id}&report=final&reportType=final` |

- 로컬 서버: `python scripts/serve_mock_trading.py` → `http://127.0.0.1:8080/template/dashboard_desktop/`
- HTML 섹션: **REPLAY 최종 결과** (`data-ui="final-report-section"`) — `finalReport` payload 있을 때만 표시

---

## F. 검증 완료 사례

### Smoke 체결 (20241218)

**run_id:** `replay_20241218_16b6f721`

| 항목 | 결과 |
|------|------|
| decision_at | 2024-12-18T15:30:00+09:00 |
| fill_date | 20241219 |
| leakage_summary | PASS |
| 체결 | B/C 대한전선 5주@11,430원, D 루닛 5주@34,311원 |
| fill_price_source | `pykrx_open_by_ticker` |
| LIVE 변경 | 없음 |

> `20260522` 등 미래·체결 불가 일자는 smoke 부적합.

### Short campaign

**campaign_id:** `short_5days_20241210_20241216_8b2e0d`  
- weekly: `w50`, `w51`  
- monthly: `m202412`

### Full audit (2026-01~04)

- **코드:** 종료·최종 리포트·Slack 최종 경로 구현됨
- **실행:** 저장소에 **Jan~Apr 2026 전체 완주 campaign 아직 없음** (거래일 수백 일, CI/장시간 실행 필요)
- 완주 시: 4월 마지막 거래일 처리 후 자동 종료 → `final.json` + Slack 최종 1건

---

## G. Full audit 종료 및 최종 종합 리포트

### 종료 조건

1. `replay_type=full_audit`
2. 처리 마지막 거래일 `dates[-1]` ≥ 4월 말 **마지막 KRX 거래일** (`is_full_audit_complete`)
3. `REPLAY_MAX_DAYS` 미사용 또는 전체 거래일 포함

### 종료 처리 (`finalize.py`)

- 보유종목 **강제 매도 없음**
- 4월 마지막 거래일 **종가** (`close_price_krw`) 또는 검증 가능 fallback 가격으로 평가
- `competition_status: ended`, `decisions_frozen: true`
- 이후 동일 campaign / 기간 외 일자에 `run_replay_single_day` → 거부

### 최종 리포트 포함 항목 (`final_report.py`)

| 섹션 | 필드 |
|------|------|
| 기간 | `period` — 2026-01-01 ~ 2026-04-30 |
| 팀 순위 | `teams[]` — 최종 총자산, 누적수익률, 순위 |
| 월간 흐름 | `monthly_flow` — 팀별 월간 end_assets / return_pct |
| 판단 | `best_decision`, `worst_decision` |
| 매도 | `sell_evaluation` |
| 벤치마크 | `benchmark` — KOSPI 60% + KOSDAQ 40%, 팀별 alpha |
| 감사 집계 | `audit_counts` — 침범·규칙위반·미검증 근거 건수 |
| 위원회 | `committee_verdicts` (run_audit_ai 시 AI verdict 병합) |
| LIVE | `live_readiness` — `live_ready`, `conclusion`, `blockers` |

저장: `campaigns/{id}/reports/final.json`  
Firestore: `competition_replay_final_reports/{report_id}` (`rfr_{campaign_id}`)

---

## H. Slack 정책

| 허용 | 금지 |
|------|------|
| 주간 리포트 링크 (campaign 주차별) | smoke 요약 |
| 월간 리포트 링크 | 개별 매수·매도 알림 |
| **full_audit 종료 시 최종 리포트 링크 1건** | replay 진행 상태 메시지 |
| 치명적 실패 (`send_fatal_replay_error`) | |

**최종 Slack 형식**

```
[2026년 1~4월 AI 투자대결 최종 리포트]

박성범님, AI 투자 에이전트의 리플레이 투자대결이 종료되었습니다.
최종 실적과 감사 결과를 확인해 주세요.

버튼: 최종 리포트 확인하기
```

환경변수: `COMPETITION_SLACK_WEBHOOK` ← `SLACK_WEBHOOK_TRADING` ← `SLACK_WEBHOOK_URL`

---

## I. 실행 방법

### 로컬 CLI

```bash
# Smoke (체결 검증용 날짜)
python scripts/run_competition_replay.py --replay-type smoke_1day --date 20241218

# Short / Month
python scripts/run_competition_replay.py --replay-type short_5days --date 20241210
python scripts/run_competition_replay.py --replay-type month --date 20241201

# Full audit (고정 2026-01-01 ~ 2026-04-30, 장시간)
python scripts/run_competition_replay.py --replay-type full_audit --run-audit-ai
# Slack 포함: --no-slack 생략 (기본 campaign에서 send_slack_reports=True)

# 개발용 일부만 (종료·최종 리포트 없음)
set REPLAY_MAX_DAYS=5
python scripts/run_competition_replay.py --replay-type full_audit --mock-llm
```

### GitHub Actions

**Workflow:** `AI 투자 경쟁 리플레이 검증` (`.github/workflows/competition_replay_audit.yml`)

| Input | 설명 |
|-------|------|
| `replay_type` | smoke_1day / short_5days / month / full_audit / custom |
| `start_date` | YYYYMMDD (full_audit는 무시) |
| `end_date` | month/custom용 |
| `send_slack_reports` | 주간·월간·(full_audit 완주 시) 최종 링크 |
| `run_audit_ai` | 마지막 거래일 감사위원회 AI |
| `use_mock_llm` | API 호출 생략 |
| `persist_replay_results` | `data/competition/replay/` artifact 업로드 |

---

## J. 테스트

```bash
python -m unittest discover -s tests/competition -p "test_replay*.py" -v
python -m unittest tests.competition.test_workflow_safety -v
```

| 스위트 | 건수 (2026-05-24) |
|--------|-------------------|
| `test_replay*.py` | 22 OK |
| `test_workflow_safety` | 10 OK |
| **합계** | **32 OK** |

---

## K. 알려진 제한·미완

| 항목 | 설명 |
|------|------|
| Full audit 실제 완주 | 2026-01~04 전 거래일 REPLAY 미실행 — CI 또는 전용 러너에서 `full_audit` 장시간 실행 필요 |
| 벤치마크 | pykrx 지수 OHLCV는 KRX 로그인·네트워크 필요; 실패 시 `benchmark.verified=false`, LIVE readiness blocker |
| 팀 B DART | 시점 제한 evidence — full replay 시 추가 검증 권장 |
| 일부 fill 실패 | 특정 일자·종목 `fill_price_missing` — `limitations`에 기록 |
| Firebase 로컬 | credentials 없으면 Firestore sync skip, 로컬 JSON만 |
| 비용 모델 | `costs_not_implemented` — 수수료·세금 미반영 |

---

## L. LIVE schedule 복구 (REPLAY 승인 후)

1. `.github/workflows/competition_auto_ops.yml` 상단 **Restore LIVE** 주석 블록 참고
2. `workflow_dispatch` inputs 복구 (git `ba1683f` 이전 참고)
3. `schedule:` cron 주석 해제
4. `COMPETITION_LIVE_SCHEDULE_DISABLED` → `"0"` 또는 제거
5. session/init/trigger/Slack 단계 복구
6. `COMPETITION_ALLOW_LIVE_SESSION=1` 설정
7. **검증은 계속** `AI 투자 경쟁 리플레이 검증` workflow 사용

### LIVE workflow 현재 동작 (중지 기간)

- 표시명: **`LIVE 자동 운용 (현재 중지됨)`**
- Run → 중지 안내 + readiness JSON만 (`sys.exit(0)`)
- session / Slack / Firebase 쓰기 / seed reset **없음**
- inputs 체크박스 **없음**

---

## M. 체크리스트 (LIVE 재개 전)

- [ ] `full_audit` 2026-01-01 ~ 2026-04-30 **전 거래일** 완주
- [ ] `reports/final.json` 생성, `competition_status=ended`
- [ ] 최종 리포트 `live_readiness.live_ready=true` (침범 0, 규칙위반 0, 벤치마크 검증)
- [ ] 대시보드 최종 URL·Slack 최종 링크 수동 확인
- [ ] `COMPETITION_ALLOW_LIVE_SESSION=1` + LIVE workflow 복구
- [ ] LIVE seed / Firestore 계좌 상태 점검

---

*관련 문서: `docs/CURSOR_NONSTOP_REPLAY_AUDIT_IMPLEMENTATION_PROMPT.md`, `docs/ai_trading_competition/`*
