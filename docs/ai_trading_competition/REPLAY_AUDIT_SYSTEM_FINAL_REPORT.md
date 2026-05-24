# REPLAY / AUDIT 시스템 최종 리포트

**작성일:** 2026-05-24  
**기준 commit:** (push 후 갱신)  
**판정:** **REPLAY smoke 실행 가능 / LIVE는 아직 중지**

---

## A. 최종 판정

**REPLAY smoke 실행 가능 / LIVE는 아직 중지**

- LIVE 자동 `schedule` cron 비활성화 완료
- REPLAY 전용 저장 경로 `data/competition/replay/{replay_run_id}/` 분리 완료
- Point-in-time snapshot + 코드 감사기(미래 데이터 차단) 구현 완료
- 2026-05-22 장 마감 smoke 1회 로컬 실행 완료 (`replay_20260522_f547e8c7`)
- 다음 거래일(20260526) 체결 원칙 적용 — **당일 종가 동시 체결 없음**
- 일부 종목 다음 거래일 OHLCV 조회 실패로 체결 미완료 (데이터 한계, P1)
- 대시보드 REPLAY 탭 미연결 (P1)
- 감사·평가 AI 2인조: 선택적 (`--run-audit-ai`), smoke 기본 off

**LIVE 자동운용 시작 금지** — `COMPETITION_ALLOW_LIVE_SESSION=1` 및 schedule 복구 전까지.

---

## B. 실제 변경 파일 목록

| 파일 | 구분 | 목적 |
|------|------|------|
| `src/trading/competition/runtime.py` | 신규 | execution_mode, LIVE 차단, replay 경로 |
| `src/trading/competition/replay/*` | 신규 | snapshot, leakage audit, code auditor, runner, store |
| `src/trading/competition/audit/committee.py` | 신규 | 평가 AI 2인조 (선택) |
| `src/trading/competition/ops/session.py` | 수정 | LIVE session 가드 |
| `src/trading/competition/teams/engine.py` | 수정 | REPLAY 프롬프트(스냅샷 only) |
| `src/trading/competition/teams/schemas.py` | 수정 | order_type 정규화 |
| `src/trading/competition/models.py` | 수정 | `run_mode`, `seed_run` |
| `src/trading/competition/execution/executor.py` | 수정 | seed/replay 메타·타임스탬프 |
| `.github/workflows/competition_auto_ops.yml` | 수정 | schedule 중지, `COMPETITION_LIVE_SCHEDULE_DISABLED` |
| `.github/workflows/competition_replay_audit.yml` | 신규 | REPLAY 수동 workflow |
| `scripts/run_competition_replay.py` | 신규 | REPLAY CLI |
| `scripts/reset_competition_seed.py` | 기존 | LIVE seed 초기화 (유지) |
| `tests/competition/test_replay_audit_system.py` | 신규 | REPLAY/AUDIT 단위·정적 테스트 |
| `tests/competition/test_workflow_safety.py` | 수정 | schedule 중지 검증 |

기존 `scripts/run_competition_historical_seed.py` / `historical_seed.py`는 **레거시 seed run**이며, 신규 검증 경로는 **`run_competition_replay.py`** 사용.

---

## C. 기존 설계 대비 변경점

| 항목 | 내용 |
|------|------|
| LIVE 보존 | `data/competition/`(또는 `live/`) 기존 계좌·대시보드 경로 유지, REPLAY가 쓰지 않음 |
| REPLAY 추가 | `replay_smoke` / `replay_audit`, 격리 저장, 다음 거래일 체결 규칙 |
| AUDIT 추가 | 코드 감사기 + 선택적 평가 AI |
| schedule | **중지됨** (cron 주석 + env 플래그) |
| 저장 분리 | `data/competition/replay/{id}/` — Firestore replay 컬렉션은 후속(P1) |

---

## D. 실행 흐름

### LIVE workflow (`competition_auto_ops.yml`)
- `workflow_dispatch`만: `test_slack`, `test_market_closed_notice`, `reset_competition_seed`, dry-run
- **schedule 없음** → 자동 live session 없음
- `run_competition_session` 호출 시 `assert_live_session_allowed()` → 기본 **거부**

### REPLAY workflow (`competition_replay_audit.yml`)
- 수동만, `COMPETITION_EXECUTION_MODE=replay_smoke`
- `scripts/run_competition_replay.py --date YYYYMMDD`
- LIVE 계좌·KIS 주문·schedule **미사용**

### Slack
- `COMPETITION_SLACK_WEBHOOK` ← `secrets.SLACK_WEBHOOK_TRADING` (유지)
- REPLAY 요약: `[AI 투자 경쟁앱 / REPLAY] ...` (LIVE와 구분)

### Firebase
- REPLAY: 로컬 `data/competition/replay/` 우선 (이번 구현)
- LIVE Firestore: REPLAY runner가 **미접근**

### 대시보드
- **미연결** — live API만 `data/competition/` 읽음 (P1)

---

## E. 미래 데이터 침범 차단

### Snapshot
- `snapshot_id`, `decision_at` (장 마감 15:30 KST)
- pykrx 기반 가격·거래대금·등락률, 팀별 scout 후보
- `constraints.no_web_search`, `no_live_api_enrich`

### Evidence 메타
`evidence_id`, `source_type`, `observed_at`, `published_at`, `available_at`, `timestamp_confidence`

### 차단 규칙
- `available_at <= decision_at` AND `timestamp_confidence == verified` (포함 evidence)
- 뉴스: `news_unverified` — B팀 정식 성과 근거 **불가**
- 판단 전 `code_auditor` + `leakage_audit`

### 한계
- AI 모델 **사전지식** 오염은 코드로 차단 불가
- DART 과거 공개시각 replay: **미구현** (B팀 liquidity only)
- 장중 분봉 replay: **미구현**

---

## F. 팀별 replay 평가 가능 범위

| 팀 | 데이터 | smoke 20260522 결과 |
|----|--------|---------------------|
| A | pykrx TV·등락률 | HOLD (DeepSeek) |
| B | 유동성 scout, 뉴스 미검증 | BUY 판단, 체결 실패(시세) |
| C | pykrx + 외국인 수급(verified) | HOLD |
| D | rebound scout | BUY 판단, 체결 실패(시세) |

---

## G. 감사·평가위원회

| 구성 | 상태 |
|------|------|
| 코드 감사기 | **구현 완료** |
| 총괄 평가 AI | **선택 구현** (`--run-audit-ai`) |
| 반론 검토 AI | **선택 구현** |

코드 FAIL 시 AI가 덮어쓰지 않음.

---

## H. 테스트 결과

실행: `python -m unittest tests.competition.test_replay_audit_system tests.competition.test_workflow_safety tests.competition.test_historical_seed`

- **통과:** 26+
- **실패:** 0 (로컬 기준)

---

## I. Smoke Replay 결과

**run_id:** `replay_20260522_f547e8c7`

| 항목 | 결과 |
|------|------|
| decision_at | 2026-05-22T15:30:00+09:00 |
| fill_date (다음 거래일) | 20260526 (석가탄신일 5/25 스킵) |
| leakage_summary | PASS |
| LIVE accounts 변경 | 없음 (`affects_live_account: false`) |
| 체결 | B/D: pykrx 시세 조회 실패 → 미체결 |
| Slack (이전 run) | ok (로컬 webhook) |

**당일 종가 체결 없음** — `fill_date` > `trading_date` 확인됨.

---

## J. P0 / P1 / P2

### P0 (LIVE 시작 전)
- schedule 복구 전 **full replay short/month** 검증
- 다음 거래일 시세 조회 안정화 (또는 실패 시 pending만 저장)
- LIVE Firestore와 REPLAY 컬렉션 분리 업로드

### P1
- 대시보드 REPLAY 탭
- DART point-in-time (B팀)
- `short_5days` / `month` runner

### P2
- Full audit 2026-01~04
- Firestore replay 문서 purge 도구

---

## K. 다음 실행 순서

1. **replay smoke** — Actions: `AI 투자 경쟁 리플레이 검증`, `replay_type=smoke_1day`, `start_date=20260522`
2. 5거래일 replay (`short_5days` — 경로 준비 후)
3. 1개월 replay
4. 2026-01-01~04-30 full audit
5. audit 통과 후 `COMPETITION_ALLOW_LIVE_SESSION=1` + schedule 복구

---

## LIVE schedule 복구 방법

1. `.github/workflows/competition_auto_ops.yml`에서 `schedule:` 블록 주석 해제
2. `env.COMPETITION_LIVE_SCHEDULE_DISABLED` 제거 또는 `"0"`
3. readiness + replay short 검증 후 `COMPETITION_ALLOW_LIVE_SESSION=1` 설정
