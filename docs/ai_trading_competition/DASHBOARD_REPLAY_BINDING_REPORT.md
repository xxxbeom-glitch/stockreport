# REPLAY · 기본셋 대시보드 1:1 통합 보고서

작업일: 2026-05-25 (2차)  
목적: REPLAY 전용 AUDIT 메인 화면을 제거하고, LIVE와 동일한 `template/dashboard_desktop` 기본셋 렌더러에 데이터셋만 교체.

---

## 1. REPLAY 전용 화면이 생성되던 위치

| 구분 | 파일 | 내용 |
|------|------|------|
| DOM | `template/dashboard_desktop/index.html` | `<section data-ui="audit-panel">`, `replay-decisions-card`, `mode-banner`, `monthly-report-section`, `final-report-section` |
| JS 렌더 | 동일 파일 | `renderReplayAudit()`, `renderReplayDecisions()`, `refreshDashboard()` 내 REPLAY 분기 호출 |
| 데이터 | `replay_payload.py` | `auditSummary`, `teamDecisions` (메인 UI용이 아닌 감사용) |
| 공개 JSON | `pages_publish.py` | sanitize 시 audit 필드 strip (Pages용) |

**문제 구조 (수정 전)**

```text
LIVE → mock/ API payload → refreshDashboard()
REPLAY → 동일 HTML + audit DOM 표시 + renderReplayAudit/Decisions
```

---

## 2. 공통 기본셋 렌더러로 통일한 방식

**수정 후 구조**

```text
공통 기본셋 (index.html 단일 DOM + refreshDashboard)
 ├─ dataMode=live  → loadLiveDashboard() → applyCompetitionPayload()
 └─ dataMode=replay → loadReplayDashboard() → applyCompetitionPayload()
```

- AUDIT/월간/최종 섹션 **HTML에서 삭제** (CSS `display:none` 임시처리 아님).
- `applyCompetitionPayload()`가 LIVE/REPLAY 공통 진입점.
- `getAgentPeriodStats()`, `updateKpis()`, `syncAgentTilesFromMeta()`, `rebuildStockTable()`, `renderTradeHistory()`, `updateChart()` 모두 동일 함수 — `competitionLoaded` + payload만 교체.
- REPLAY 전용 렌더 함수(`renderReplayAudit`, `renderReplayDecisions`) **삭제**.

---

## 3. 제거한 메인 UI 영역

1. `REPLAY · AUDIT 요약` 카드 그리드 전체  
2. `팀별 판단 근거 · 목표가` 테이블 전체  
3. `월간 성과 평가 리포트` 섹션  
4. `REPLAY 최종 결과` 섹션  
5. 가로 전체 `mode-banner` (REPLAY 테스트 안내 배너)  
6. 종목별 수익률 **목표가 컬럼** (기본셋에 없던 추가 컬럼 제거)

REPLAY run 셀렉트 옆 `LIVE 미반영` 보조 텍스트만 유지 (tooltip).

---

## 4. 기본셋 UI ↔ JSON 필드 매핑

| UI 영역 | JSON 필드 |
|---------|-----------|
| 헤더 메타 (REPLAY) | `replayMeta.tradingDate` → 기준일, 고정 `초기 시드 500,000원`, `REPLAY 운용 중` |
| KPI 총 자산 | `totalAssets` (= Σ `agentMeta.*.totalAssetsKrw`) |
| KPI 누적 수익률 | `(totalAssets − 2,000,000) / 2,000,000` |
| KPI 거래가능금액 | `cashAmount` |
| KPI 최고 수익 에이전트 | `agentMeta.*.returnPct` — **동률 시** `공동 1위 · N개 팀` (`bestAgentKey: null`) |
| KPI 최고 수익 종목 | `stockCatalog.*.all.returnPct` — 동률 시 `종목명 외 · 동률` |
| 차트 | `timeline.labels`, `timeline.series[].data` |
| 에이전트 카드 | `agentMeta`: name, badge, totalAssetsKrw, returnPct, cashKrw + 고정 전략 라벨(기본셋 문구) |
| 종목별 수익률 | `stockCatalog` (보유 qty>0만 payload 생성) |
| 매수·매도 | `tradeHistory` (체결만: `fill_price_krw`, `quantity`, `trade_id`/`executed_at`) |
| 주간 리포트 | `weeklyReports` — 없으면 빈 문구만 |
| 알림 | `notifications` — 없으면 뱃지 0 |

---

## 5. `replay_20241218_16b6f721` 검증 결과

| 항목 | 기대 | 결과 |
|------|------|------|
| 총 자산 | 2,000,000원 | ✅ |
| 거래가능금액 | 1,714,145원 | ✅ |
| 최고 수익 에이전트 | 0.00% · 공동 1위 · 4개 팀 | ✅ (동률 처리) |
| 최고 수익 종목 | 0.00% · 대한전선 외 · 동률 | ✅ |
| 에이전트 1호 보유 | 없음 | ✅ (기본 필터 agent1) |
| 에이전트 2호 | 대한전선 | ✅ |
| 에이전트 3호 | 대한전선 | ✅ |
| 에이전트 4호 | 루닛 | ✅ |
| 체결 3건 | B/C/D 매수 | ✅ |
| AUDIT 문자열 메인 노출 | 없음 | ✅ |
| 주간 리포트 | 빈 문구만 | ✅ |

---

## 6. 수정 파일

- `template/dashboard_desktop/index.html` — DOM 삭제, 공통 렌더, KPI 동률, agent1 기본 필터
- `src/trading/competition/dashboard/replay_payload.py` — 동률 `bestAgentKey`, mock reason 정제
- `docs/ai_trading_competition/DASHBOARD_REPLAY_BINDING_REPORT.md` (본 문서)

---

## 7. 빈 상태로 남는 영역

- 주간 성과 리포트 (해당 run에 `weeklyReports: {}`)
- 에이전트 1호 종목별 수익률 (HOLD, 보유 없음 — **정상**)
- 알림 (REPLAY payload `notifications: []`)

---

## 8. 캡처 / 확인 방법

로컬:

```bash
python scripts/serve_mock_trading.py
```

브라우저: `/template/dashboard_desktop/?mode=replay&replay_run_id=replay_20241218_16b6f721`

GitHub Pages: `main` 배포 후 동일 경로 + `docs/replay-data` JSON.

스크린샷 자동화: `scripts/capture_competition_dashboard.mjs` (필요 시 REPLAY run 인자로 실행).

---

## 9. 남은 작업

- 개발자용 AUDIT 전용 페이지 분리 (데이터는 `replay_payload` / Firestore에 유지)
- 캠페인 다일 스냅샷이 늘어나면 `timeline`만 확장 (UI 구조 변경 없음)
- 주간 리포트 생성 후 `weeklyReports` publish 연동
