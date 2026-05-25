# SIMPLE_REPLAY 구현 계획

## 조사 요약

- 대시보드 페이로드: `src/trading/competition/dashboard/payload.py` (LIVE), `replay_payload.py` (advanced REPLAY)
- AI 호출: `src/trading/competition/teams/engine.py` + `agents/gemini_client.py` / `deepseek_client.py`
- 후보 스카우트: `src/trading/competition/decision/strategy_scouts.py`
- 거래일/가격: `src/trading/competition/replay/data_provider.py`, `market_data.py`
- 정적 유니버스: `data/competition/universe/static_ticker_master.json`
- Pages 배포: `docs/replay-data/` (advanced), 신규 `docs/simple-replay-data/`

## 재사용

| 파일 | 용도 |
|------|------|
| `strategy_scouts.py` | 팀별 후보 5/5/5/3 |
| `data_provider.py` | 거래일·OHLCV (KIS/pykrx, 캐시) |
| `historical_seed.enrich_universe_historical` | 기준일 스냅샷 (상위 N종만) |
| `universe_replay.load_static_ticker_master` | 마스터 로드 |
| `teams/config.resolve_model` | LLM 라우팅 |
| `template/dashboard_desktop/index.html` | 기본셋 UI (모드만 확장) |

## 신규 파일

- `src/trading/simple_replay/` — runner, universe, llm, leakage, virtual_buy, evaluation, dashboard, report, publish, storage
- `scripts/run_simple_replay.py`
- `scripts/publish_simple_replay_pages.py`
- `.github/workflows/simple_replay.yml`
- `template/dashboard_desktop/simple-replay-pages-data.js`
- `tests/simple_replay/`

## 수정

- `scripts/serve_mock_trading.py` — simple-replay API
- `template/dashboard_desktop/index.html` — LIVE / SIMPLE REPLAY 모드 (advanced REPLAY 숨김 또는 별도 탭)

## 체크리스트

- [x] 구현 계획 문서
- [x] 백업 브랜치 `backup/advanced-before-simple-replay`
- [x] SIMPLE_REPLAY 단일 실행 runner
- [x] 미래 데이터 차단
- [x] 대시보드 페이로드 + Pages publish
- [x] UI SIMPLE REPLAY 모드
- [x] GitHub Actions workflow
- [x] 단위 테스트
- [x] 2026-01-02 기준 통합 실행 (`simple_replay_20260102_fecbc938`)
- [x] 최종 보고서

## 완료 조건

`status=completed`, AI 4팀 BUY/SKIP, 가상매수·5거래일 평가·리포트·대시보드 JSON, incomplete run 미노출.
