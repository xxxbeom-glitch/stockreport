# SIMPLE_REPLAY 최종 보고서

## 1. 결론

**SIMPLE_REPLAY 파이프라인은 구현·단일 실행·대시보드 연동·Pages JSON 발행까지 완료되었습니다.**

| 항목 | 상태 |
|------|------|
| 단일 실행 (resume/checkpoint 없음) | 완료 |
| AI 4팀 실제 LLM 호출 (DeepSeek/Gemini) | 완료 (`used_mock: false`) |
| 2026-01-02 기준 5거래일 스케줄·평가 데이터 | 완료 |
| `status=completed` run 발행 | `simple_replay_20260102_fecbc938` |
| 기본셋 대시보드 바인딩 | 완료 (LIVE / SIMPLE REPLAY 모드) |
| GitHub Actions workflow | `.github/workflows/simple_replay.yml` 추가 |

**이번 검증 run 결과:** 4팀 모두 **SKIP** (팩트·DART·후보 메타 부족으로 BUY 미선택). 가상매수·종목별 수익률은 없으나, 스펙상 유효한 완료 run이며 KPI·차트·리포트는 “추천 없음” 상태로 정상 표시됩니다.

### 사용자가 해야 할 단 한 가지 (배포)

로컬에서 검증·JSON 생성이 끝났다면, **GitHub에 push한 뒤** Actions에서 workflow **「간단 추천 검증 실행 (5거래일)」** 를 `추천 기준일=20260102` 로 실행하거나, `main` push 후 Pages 배포가 돌아가게 하면 됩니다. (원격 push 권한이 없으면 팀 계정으로 push만 수행.)

---

## 2. 기존 코드 보존

- 백업 브랜치: `backup/advanced-before-simple-replay` (현재 `main` 스냅샷)
- advanced REPLAY / competition / 주문 엔진 / audit 코드: **삭제 없음**
- UI: advanced REPLAY 탭은 `?mode=replay` 로만 접근 (기본 탭은 LIVE + **SIMPLE REPLAY**)
- 데이터: `data/competition/replay/` 와 `docs/replay-data/` 와 분리 → `data/simple_replay/`, `docs/simple-replay-data/`

---

## 3. SIMPLE_REPLAY 동작 구조

```text
추천 기준일 (decision_date)
  → static master 상위 50종 + pykrx bulk OHLCV (KIS 전종목 스윕 없음)
  → 팀별 스카우트 (A/B/C/D, 최대 5/5/5/3)
  → 실제 LLM BUY | SKIP (미래 데이터 cutoff 검증)
  → buy_date = 다음 거래일, 시가 가상매수 (BUY만)
  → evaluation_dates 5일 종가 평가
  → dashboard.json + 5일 성과 리포트 (weeklyReports.sr1)
  → docs/simple-replay-data/ 발행 (completed 만 index 노출)
```

저장 필드: `decision_date`, `buy_date`, `evaluation_dates[]`, `status`, `cost_model_applied: false`

---

## 4. AI 에이전트 실행 결과 (20260102 run)

| 팀 | Provider | Model | 결과 | reason_label |
|----|----------|-------|------|----------------|
| 1호 A | deepseek | deepseek-reasoner | SKIP | 후보 부족 |
| 2호 B | deepseek | deepseek-reasoner (Gemini 실패 후 fallback) | SKIP | 재료 부족 |
| 3호 C | deepseek | deepseek-reasoner | SKIP | 근거 부족 |
| 4호 D | deepseek | deepseek-reasoner | SKIP | 후보 없음 |

- **mock 미사용** (`used_mock: false`)
- BUY 종목 없음 → 가상매수·종목 수익률 테이블 빈 상태 (UI: “추천하여 가상매수한 종목이 없습니다.”)

---

## 5. 실제 생성된 테스트 결과

| 항목 | 값 |
|------|-----|
| run_id | `simple_replay_20260102_fecbc938` |
| 추천 기준일 | 20260102 |
| 가상매수일 | 20260105 |
| 평가 거래일 | 20260105 ~ 20260109 (5일) |
| 팀별 최종 자산 | 각 500,000원 (전원 SKIP) |
| 총 자산 | 2,000,000원 |
| 포트폴리오 수익률 | 0% |
| 최고 수익 에이전트 | 공동 1위 · 4개 팀 |
| 최고 수익 종목 | 추천 종목 없음 |

---

## 6. 데이터 신뢰성

| 검증 | 결과 |
|------|------|
| 미래 데이터 차단 | `future_data_leakage_checked: true`, 침범 시 run 실패 |
| 실제 LLM | DeepSeek reasoner (B팀 Gemini 실패 시 DeepSeek fallback) |
| mock 완료 결과 노출 | 금지 (`SIMPLE_REPLAY_ALLOW_MOCK` 없으면 mock 시 실패) |
| KIS 80회 스윕 | **미사용** (pykrx bulk + BUY 종목만 시가/종가 조회) |
| incomplete run 대시보드 | index에 `status=completed` 만 포함 |

---

## 7. 대시보드 연결

- **UI 구조:** `template/dashboard_desktop/index.html` 기본셋 유지
- **모드:** LIVE | SIMPLE REPLAY (`simple-replay-pages-data.js` + API)
- **KPI:** 총자산 200만, 공동 1위, 추천 종목 없음 — 페이로드 필드 매핑
- **차트:** 5거래일 `total_asset` (전원 50만 플랫)
- **종목 수익률 / 매수 기록:** BUY 없어 빈 상태
- **주간 성과 평가 리포트:** `weeklyReports.sr1` 실제 판단·SKIP 사유 기반 문장
- **제거·비노출:** advanced REPLAY 기본 탭 제거, audit/월간/배너 미사용

로컬 API:

- `GET /api/trading-competition/simple-replay/runs`
- `GET /api/trading-competition/simple-replay/dashboard?run_id=...`

---

## 8. 수정·생성 파일

### 생성

- `src/trading/simple_replay/` (runner, universe, llm, evaluation, dashboard, publish, api, …)
- `scripts/run_simple_replay.py`, `scripts/publish_simple_replay_pages.py`
- `.github/workflows/simple_replay.yml`
- `template/dashboard_desktop/simple-replay-pages-data.js`
- `tests/simple_replay/*`
- `docs/simple_replay/SIMPLE_REPLAY_IMPLEMENTATION_PLAN.md`
- `docs/simple-replay-data/` (실행 결과 JSON)

### 수정

- `scripts/serve_mock_trading.py` — simple-replay API
- `template/dashboard_desktop/index.html` — SIMPLE REPLAY 모드·run 선택·KPI 메타

---

## 9. 테스트

```bash
python -m unittest discover -s tests/simple_replay -q
# Ran 9 tests — OK

python scripts/run_simple_replay.py --decision-date 20260102 --observation-days 5 --force
# ok: true, run_id: simple_replay_20260102_fecbc938
```

---

## 10. 남은 문제·개선

1. **BUY가 0건인 run** — 후보 JSON에 DART/뉴스 본문·수급 수치를 넣으면 BUY·가상매수·수익률 데모가 풍부해짐 (advanced 이벤트 파이프라인 선택 연동).
2. **Gemini 모델명** — `gemini-2.5-flash-lite` 등 env 정합; 실패 시 DeepSeek fallback 동작 확인됨.
3. **GitHub Actions** — `KRX_ID`/`KRX_PW` 없으면 pykrx bulk 실패 가능 → secrets 또는 KIS-only 소량 enrich fallback 문서화.
4. **advanced short_5days** — 별도 이슈(80 KIS budget); SIMPLE_REPLAY와 데이터·UI 완전 분리됨.

---

*보고서 작성: 2026-05-25*
