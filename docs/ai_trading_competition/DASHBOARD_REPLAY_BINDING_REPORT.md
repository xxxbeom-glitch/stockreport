# 대시보드 REPLAY 데이터 바인딩 보고서

작업일: 2026-05-25  
목적: `template/dashboard_desktop` 기본셋(투자 성과 화면) 구조를 유지한 채 REPLAY 실제 데이터만 바인딩. AUDIT/개발용 UI는 메인에서 제거(데이터는 유지).

---

## 1. 수정한 파일 목록

| 파일 | 변경 요약 |
|------|-----------|
| `template/dashboard_desktop/index.html` | AUDIT/월간/최종 섹션 숨김, REPLAY KPI·타일·차트·보유종목·체결·주간 리포트 바인딩 수정, 목표가 컬럼 추가 |
| `src/trading/competition/dashboard/replay_payload.py` | 에이전트 표시명, 체결 필터, 목표가/근거 정제, mock detail 제거 |
| `src/trading/competition/replay/pages_publish.py` | 공개 JSON에서 `auditSummary`/`teamDecisions`/`campaignValidation` 제거 |
| `docs/replay-data/runs/replay_20241218_*/dashboard.json` | publish 스크립트로 재생성 |
| `tests/competition/test_replay_dashboard_payload.py` | 체결 필터·표시명·목표가 테스트 추가 |
| `tests/competition/test_pages_publish.py` | sanitize strip 키 검증 확장 |

---

## 2. 기존 기본셋 복구/유지

- **레이아웃**: 헤더 → KPI 4개 → 에이전트 자산 비교(차트+타일) → 종목별 수익률 / 매수·매도 기록 → 주간 리포트. 변경 없음.
- **제거(메인 UI)**: `REPLAY · AUDIT 요약`, 팀별 raw 판단 테이블, 월간 리포트, REPLAY 최종 결과, mode 배너 — CSS `display: none !important` + 렌더 호출 제거.
- **REPLAY 선택**: 헤더 우측 `REPLAY run` 셀렉트만 유지. GitHub Pages에서는 LIVE/REPLAY 세그먼트 숨김.
- **다크 테마·카드·상승 빨강/하락 파랑**: 기존 스타일 유지.

---

## 3. UI 영역별 JSON 필드 매핑

| UI 영역 | JSON 필드 | 비고 |
|---------|-----------|------|
| 헤더 메타 | `replayMeta.tradingDate`, `competitionStatus` | `기준일 · 초기 시드 500,000원 · 운용 {status}` |
| KPI 총 자산 | `totalAssets`, `INITIAL_TOTAL_SEED`(4×50만) | 누적 수익률 = (totalAssets − 200만) / 200만 |
| KPI 거래가능금액 | `cashAmount` | 4팀 현금 합 |
| KPI 최고 수익 에이전트 | `bestAgentKey`, `bestAgentReturnPct`, `agentMeta[*]` | |
| KPI 최고 수익 종목 | `bestStockName`, `bestStockReturnPct`, `stockCatalog` | 보유 중 평가수익률 최대 |
| 차트 | `timeline.labels`, `timeline.series[].data` | manifest `accounts.total_assets_krw` 스냅샷 |
| 에이전트 타일 | `agentMeta`: name, badge, strategy, cashKrw, totalAssetsKrw, returnPct | |
| 종목별 수익률 | `stockCatalog[code]`: name, agents, all.avg/current/returnPct/pnl, targetPrice, reason | `manifest.accounts.positions` |
| 매수·매도 기록 | `tradeHistory[agent*]` | `trades.jsonl` 중 체결만 (`fill_price_krw`>0, `quantity`>0, trade_id/executed_at) |
| 주간 리포트 | `weeklyReports` | 없으면 `아직 생성된 주간 리포트가 없습니다.` |

**공개 Pages JSON** (`docs/replay-data/`): 위 필드만 노출. `auditSummary`, `teamDecisions`, `teams` status 문자열은 제거.

---

## 4. 아직 비어 있거나 제한적인 영역

| 영역 | 상태 |
|------|------|
| 주간 리포트 | `replay_20241218_*` — `weeklyReports: {}` → 빈 문구만 표시 |
| 월간 리포트 | 메인에서 섹션 제거 |
| KPI 누적 수익률 (smoke run) | 체결 직후 평가가 동일가 → 0% (목업 아님, 실제 값) |
| 알림 | REPLAY payload `notifications: []` |
| 장기 캠페인 미체결 run | `stockCatalog`/`tradeHistory` 빈 경우 — `-` / 빈 테이블 |

---

## 5. 체결 → 보유종목 → 자산 → 차트 검증

**검증 run**: `replay_20241218_16b6f721`

1. **매수 체결** (B/C/D): `trades.jsonl` → `tradeHistory.agent2/3/4` 각 1건.
2. **현금 감소**: `agentMeta` cashKrw 442,850 / 328,445 등 manifest `accounts`와 일치.
3. **보유종목**: `stockCatalog` — 001440 (agent2,3), 328130 (agent4). `targetPrice` 54,000.
4. **총자산**: 팀별 500,000 (= 현금 + 평가). KPI `totalAssets` 2,000,000.
5. **차트**: labels `12.18`, `12/19`; series data `[500000, 500000]` — 동일가라 수평선(정상).
6. **UI 버그 수정**: 기본 필터 `agent1` → 보유 없음 표시 문제 → **첫 보유 팀으로 자동 필터** (`pickDefaultStockAgent`). REPLAY 체결 목록은 `dayIndex` 필터 제거.

---

## 6. REPLAY 렌더링 최종 확인 (체크리스트)

| 항목 | 결과 |
|------|------|
| 기본셋과 동일한 메인 구조 | ✅ |
| KPI 4개 실제 데이터 | ✅ (smoke: 0% 수익률은 데이터 그대로) |
| 팀 카드 현금/총자산/수익률 | ✅ |
| 체결 매수 → 종목별 수익률 (agent2 선택 시 대한전선) | ✅ |
| 매수·매도 = 체결만 | ✅ |
| 차트 = timeline 스냅샷만 | ✅ |
| audit/debug/raw 메인 미노출 | ✅ |
| 월간 리포트 제거 | ✅ |
| 주간 미생성 시 목업 문장 없음 | ✅ |

---

## 7. 남은 문제와 다음 작업

1. **에이전트 타일 `status`**: manifest에 `filled_next_session` 등이 있으나 UI에 노출하지 않음(의도). 필요 시 별도 운용 상태 문구만 추가.
2. **캠페인 타임라인**: 다일 완료 시 `timeline`은 일자별 `total_assets_krw`만 사용. intraday 스냅샷 파일이 생기면 payload 확장 필요.
3. **주간 리포트 생성**: REPLAY batch 완료 주차에 `weeklyReports` 생성·publish 연동.
4. **개발자용 AUDIT 화면**: `auditSummary`/`teamDecisions`는 서버·Firestore·로컬 로그에 유지 — 추후 `/dev/audit` 등 분리 권장.
5. **로컬 스크린샷 검증**: `python scripts/serve_mock_trading.py` 후 `?mode=replay&replay_run_id=replay_20241218_16b6f721` 로 수동 확인 권장.

---

## 부록: 데이터 소스 경로

- 기본셋 HTML: `template/dashboard_desktop/index.html`
- Pages 로더: `template/dashboard_desktop/replay-pages-data.js`
- Payload: `src/trading/competition/dashboard/replay_payload.py`
- 공개 JSON: `docs/replay-data/index.json`, `docs/replay-data/runs/*/dashboard.json`, `docs/replay-data/campaigns/*/dashboard.json`
- 로컬 REPLAY: `data/competition/replay/{replay_run_id}/manifest.json`, `trades.jsonl`, `snapshot.json`
