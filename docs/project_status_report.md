# stockreport 진행 현황

최종 갱신: 2026-05-21

## 1. 프로젝트 목적

- 국장 관심 섹터·관심종목을 매일 확인해 **Slack으로 판단 보조 메시지**를 보내는 시스템
- **자동매매 아님** (진입·청산 실행 없음)
- **watchlist 자동 수정은 현재 중지** — 제안·리포트만 생성

## 2. 지금까지 완료된 것

- 기존 관심종목 **25개 재평가** (주간 파이프라인)
- **OHLCV·거래대금** 수집 안정화 (KIS / pykrx)
- **keep / weaken / caution / remove** 분류
- **뉴스·공시** 수집 및 Slack·리포트 이슈 연결
- **신규 후보 스캐너** (5 에이전트 투표)
- **후보군 확장** (섹터 유니버스, 우선주 제외)
- **대형주·기존 관심종목 제외** 로직
- **일별 `daily_scan`** 저장 (`data/daily_scan/`)
- **최근 5일 흐름** 기반 `trend_score` 반영
- GitHub Actions 3분리 (매일 후보 / 관심종목 재평가 / 후보 스캔 테스트)

## 3. 현재 유지하는 것

- **매일 투자 후보 알림** (KST 10:30·13:50 스케줄)
- **실제 Slack 발송** (`DAILY_PICK_AUTO_SEND=true`)
- **뉴스·공시 수집** (주간·수동 실행 시)
- **신규 후보 탐색** (제안 JSON·Slack 초안)
- **수동 dry-run** (발송·watchlist 반영 없이 확인)

## 4. 현재 중지한 것

- **관심종목 자동 수정** (`WATCHLIST_AUTO_APPLY=false`)
- **관심종목 자동 교체** (`CANDIDATE_AUTO_REPLACE=false`)
- **관심종목 재평가 자동 스케줄** (주간 cron 비활성)
- **watchlist 자동 반영** (`kr_watchlist.json` proposal만 저장)

## 5. 현재 운영 방식

| 기능 | 방식 |
|------|------|
| 매일 투자 후보 알림 | **계속 사용** — 자동 스케줄 + Slack |
| 관심종목 재평가 | **수동 확인용** — 리포트·proposal 생성, Slack 기본 꺼짐 |
| 신규 후보 | **제안만 생성** — watchlist 미반영 |
| 실제 반영 | **사람이 결정** — JSON·MD 검토 후 수동 적용 |

상세: [STOCKREPORT_OPERATIONS.md](./STOCKREPORT_OPERATIONS.md)
