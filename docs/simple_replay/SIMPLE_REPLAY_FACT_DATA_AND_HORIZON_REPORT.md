# SIMPLE_REPLAY 팩트 데이터·다중 평가기간 보강 보고서

## 결론

SIMPLE_REPLAY 구조는 유지한 채 **후보별 팩트 패키지**와 **5/10/20거래일 성과 저장**을 추가했다. 검증 run `simple_replay_20250304_d82e3123`에서 **4팀 모두 BUY**, 실제 LLM(`used_mock=false`), DART·가격·수급(외국인) 팩트가 `team_candidate_inputs.json`에 저장됨을 확인했다. UI 기본 표시는 5거래일 그대로이며 JSON에 10·20거래일 평가가 포함된다.

**커밋:** `23a4bbb` (이전 파이프라인: `1dc3213`)

---

## 1. 추가한 팩트 데이터

| 종류 | 내용 | 출처·시점 제한 |
|------|------|----------------|
| 가격·거래대금 | 5거래일 종가/거래대금, 등락률, tv_ratio, 돌파/급등/눌림 신호 | pykrx 시장 OHLCV bulk, `date <= decision_date` |
| 수급 | 외국인 순매수(원), 기관 순매수 | pykrx `get_market_net_purchases` / `get_market_trading_value_by_ticker`; 없으면 `missing` 명시 |
| DART | 제목·접수일·`source_id`·URL | Open DART `list.json`, `rcept_dt <= decision_date` |
| 뉴스 | 제목·발행시각·출처·`source_id` | Naver 검색 API, `pubDate <= decision_date 15:30 KST`, 제목 중복 제거 |

미래 데이터: `leakage.check_decision_leakage` — `supporting_facts.published_at`이 기준일 마감 이후면 run 실패.

---

## 2. AI 입력·후보 저장

- 모듈: `src/trading/simple_replay/facts.py` → `build_team_candidate_inputs()`
- 저장: `data/simple_replay/runs/{run_id}/team_candidate_inputs.json`
- 팀별 스카우트 + `fact_package` (가격/flow/dart/news 전체 JSON)

### 검증일 선정: **20250304**

| 이유 |
|------|
| 2025-03-04 이후 **20거래일** 세션 데이터 확보(20250401까지 complete) |
| DART prefetch 24종에서 **material_tickers 24개** |
| 외국인 수급 맵 **2582종** (기관 pykrx 컬럼 미지원 → `inst_net_status: missing` 명시) |
| 당일 시장 이슈(방산·2차전지 등)로 BUY 가능성 |

---

## 3. 에이전트별 결과 (`simple_replay_20250304_d82e3123`)

| 팀 | 결과 | 종목 | reason_label | supporting_facts |
|----|------|------|--------------|------------------|
| 1호 A | **BUY** | 042660 한화오션 | 거래대금 급증 & 가격 돌파 | DART 3건 + 가격 신호 |
| 2호 B | **BUY** | 009150 삼성전기 | 재료성 공시 연계 | DART(삼성전기 관련 공시) |
| 3호 C | **BUY** | 042660 한화오션 | 외국인 대량 순매수·거래대금 | flow + DART |
| 4호 D | **BUY** | 373220 LG에너지솔루션 | 눌림 후 안정화 신호 | 가격 pullback + DART |

- **BUY 4건** — 다음 거래일(20250305) 시가 가상매수 완료
- 예: A팀 한화오션 6주 @ 83,300원, 5일 수익률 **-6.36%**, 20일 구간까지 저장

### 보조 검증: 20260102 (`simple_replay_20260102_6dfa07e5`)

팩트 강화 후 재실행 — **A BUY(319400)**, **C BUY(042700)**, B/D SKIP(충분한 근거 검토 후 판단, 단순 미구현 아님).

---

## 4. 5 / 10 / 20거래일 평가

`manifest.evaluation_horizons`:

```json
"5":  { "status": "complete", "last_date": "20250311" },
"10": { "status": "complete", "last_date": "20250318" },
"20": { "status": "complete", "last_date": "20250401" }
```

`positions[].evaluations["5"|"10"|"20"]` — 각각 `daily_evaluations`, `highest_return_pct`, `lowest_return_pct`, `final_return_pct`, `target_reached_date`.

- **대시보드:** `daily_evaluations` = 5일 구간(기존 필드 유지)
- **UI 기간 전환:** 미추가(JSON만 확장)

---

## 5. 화면·데이터 분리

- 기본셋 `SIMPLE REPLAY` 모드 → `docs/simple-replay-data/runs/.../dashboard.json`
- advanced REPLAY·AUDIT 메인 DOM 미노출(구조 변경 없음)
- incomplete/failed run은 `index.json`에 `status=completed`만 노출

---

## 6. 테스트

```bash
python -m unittest discover -s tests/simple_replay -q
# Ran 10 tests — OK
```

---

## 7. 미해결·제한

| 항목 | 상태 |
|------|------|
| 기관 순매수(pykrx `기관` 컬럼) | 당일 run에서 KOSPI/KOSDAQ 모두 unavailable — `inst_net_krw: null`로 명시 |
| Naver 뉴스 | 과거 시점 필터 후 **없음**인 종목 다수 (`news_status: none_as_of_date`) — API가 최근 기사 위주 |
| KIS 호출 | 팩트 단계: DART HTTP + pykrx bulk; 평가: BUY 종목 OHLCV만 |
| inst_errors | `inst_net_unavailable:KOSPI/KOSDAQ` — pykrx API 변경 가능성, 추정값 미사용 |

---

## 8. 수정 파일

| 파일 | 역할 |
|------|------|
| `src/trading/simple_replay/facts.py` | 팩트 패키지·팀별 후보 입력 |
| `src/trading/simple_replay/calendar.py` | 5/10/20 거래일 스케줄 |
| `src/trading/simple_replay/evaluation.py` | 다중 구간 평가 |
| `src/trading/simple_replay/runner.py` | 통합·`team_candidate_inputs` 저장 |
| `src/trading/simple_replay/llm.py` | 풀 fact_package LLM 입력 |
| `tests/simple_replay/test_multi_horizon.py` | 구간 평가 테스트 |
| `scripts/run_simple_replay.py` | UTF-8 stdout |
| `docs/simple-replay-data/...` | Pages JSON (`20250304` run) |

---

*작성: 2026-05-25*
