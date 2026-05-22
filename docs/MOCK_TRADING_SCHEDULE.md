# 모의투자 스케줄·가상매수 실행

실제 자동매매가 아닌 **AI 추천 → 가상매수 → 장기 누적 성과** 비교 시스템입니다.

- 익절/손절/자동 종료 없음
- 종목당 최초 1회만 가상매수 (재추천은 이력·에이전트만 갱신)
- `week_id` / 주간 성과 기준 미사용 (전 기간 누적)

## GitHub Actions

Actions 목록에 **가상투자 자동 운영** 하나만 표시됩니다 (`mock_trading_auto_ops.yml`).

- 예약 실행: 월·목·금 15:35 판단 / 평일 09:05~19:55(10분 간격) 체결 확인 / 평일 20:05 NXT 최종 만료
- 수동 실행(Run workflow): 같은 스크립트 1회 — 대기 주문 있으면 체결 확인, 없고 판단 가능하면 주문 생성, 없으면 Slack에 사유

```powershell
python scripts/run_mock_trading_auto_ops.py
```

## 정기 AI 판단 (KST)

| 요일 | 시각 | entry_type |
|------|------|------------|
| 월 | 정규장 마감 후 **15:30+** | `REGULAR_MON` |
| 목 | 15:30+ | `REGULAR_THU` |
| 금 | 15:30+ | `REGULAR_FRI_WEEKEND` (`has_weekend_risk: true`) |

```powershell
python scripts/run_mock_trading_scheduled_judgment.py
python scripts/run_mock_trading_scheduled_judgment.py --entry-type REGULAR_MON --force
```

통과 종목 없음 → 판단 기록에 **`신규 매수 없음`** (`NO_NEW_BUYS`).

## 가상 지정가 주문 · 체결

AI가 `limit_price`(entry_price 기준)를 산정 → **주문만 생성** → 세션 중 지정가 충족 시 체결 → ledger 반영.

| 우선순위 | 조건 | 주문·체결 세션 | order_market |
|----------|------|----------------|--------------|
| 1 | NXT 가능 | 당일 **15:40~20:00** (20:00 미체결 만료, 20:05 최종 배치) | `NXT_AFTER_MARKET` |
| 2 | 불가 | **다음 거래일 09:10~15:30** | `KRX_REGULAR` |

주문 상태(`data/mock_trading/pending_executions.json`): `ORDER_PENDING` → `FILLED` | `EXPIRED_UNFILLED`

```powershell
# 세션 중 반복 실행 권장 (예: 10분 간격)
python scripts/run_mock_trading_execute_pending.py
```

NXT 판별: `MOCK_TRADING_NXT_MODE` (`heuristic`|`always`|`never`), `MOCK_TRADING_NXT_TICKERS=005930,000660`

## 실시간 감시 (자동 매수 없음)

- KIS: 현재가·거래량·등락 → 보유 종목 시세·마일스톤 갱신
- DART: 중요 공시 → 긴급 후보

```powershell
python scripts/run_mock_trading_realtime_watch.py
python scripts/run_mock_trading_intraday_judgment.py
```

## 긴급 판단

- `entry_type`: `INTRADAY_ALERT`
- `trigger_type`: `INTRADAY`
- 정기 회차와 별도 `judgment_runs/`·`pending_executions.json` 기록

## 데이터 경로

| 파일 | 용도 |
|------|------|
| `data/mock_trading/virtual_positions.json` | 누적 보유 ledger |
| `data/mock_trading/pending_executions.json` | 실행 대기열 |
| `data/mock_trading/judgment_runs/*.json` | 판단 회차 로그 |
| `data/mock_trading/intraday_alert_candidates.json` | 긴급 후보 |

## API (로컬 서버)

`python scripts/serve_mock_trading.py`

- `GET /api/trading-display` — 누적 성과 UI
- `POST /api/mock-trading/auto-ops` — 자동운영(판단·체결·Slack)
- `POST /api/mock-trading/scheduled-judgment` / `execute-pending` — 개별 단계(레거시)
