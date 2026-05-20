# 09 국장 MVP 정정·보강 결과 (08 보고서 후속)

**작업일**: 2026-05-21  
**기준 문서**: `08_KR_REPORT_FINAL_RESULT.md`  
**범위**: 국장(KR) MVP만 — 미장 템플릿·연동 제외

---

## 1. 전체 결과

| 판정 | **성공** (일부 항목은 환경·레거시 문구로 **부분성공**) |

- 라벨 2개 정책, 종목별 AI 투표(API/rules 분리), `label_voting` 통일, `stock_votes` deprecated, `window.reportData` 추가까지 **코드 반영 완료**.
- 로컬에서 `python template/kr_market/render.py`로 `index.html` 생성 확인.
- API 키가 있는 환경에서 `build_stock_label_votes` 실행 시 DeepSeek/Grok/Gemini **3건 모두 `source: api`** 확인(터미널 테스트).
- API 키 없을 때는 `label_vote_rules` → `source: rules` (구조 분리 완료).

---

## 2. 수정된 파일 목록

| 파일 | 변경 내용 | 상태 |
|---|---|---|
| `agents/label_rules.py` | 최종 라벨 2개만 (`안 사면 후회함`, `지금 사기엔 좀...`); 레거시 4라벨·매수홀드매도 매핑 | 완료 |
| `agents/label_vote_helpers.py` | 티커 정규화·메트릭 보강·Grok verdict·프롬프트용 payload | 완료 (신규) |
| `agents/label_vote_rules.py` | API 미사용 시 rules 투표 (`source: rules`, confidence) | 완료 (신규) |
| `agents/label_vote_api.py` | DeepSeek/Grok/Gemini 종목별 JSON 투표 (`source: api`) | 완료 (신규) |
| `agents/label_voting.py` | API→rules fallback, 2라벨 merge, `stock_votes` 의존 제거 | 완료 |
| `agents/stock_votes.py` | 상단 DeprecationWarning; 5인 분석가 레거시 유지 | deprecated |
| `main.py` | `label_voting` 연동; 4라벨 집계 제거 | 완료 |
| `template/kr_market/report_adapter.py` | `label_vote_helpers.normalize_ticker`; UI용 ai_votes 제거; `build_report_data_js` | 완료 |
| `template/kr_market/template.html` | AI 투표 리스트 UI 제거; `window.reportData` 스크립트 | 완료 |
| `template/kr_market/sample_data.json` | 2라벨 샘플 종목·`report_data_json` | 완료 |
| `template/kr_market/index.html` | `render.py`로 재생성 | 완료 |
| `docs/ko_stock_report_cursor_md/04_VOTING_AND_LABEL_RULES.md` | 2라벨·API/rules 구조로 정정 | 완료 |
| `docs/ko_stock_report_cursor_md/09_KR_REPORT_FIX_RESULT.md` | 본 문서 | 완료 |

---

## 3. 라벨 2개 정정 결과

### 최종 사용 라벨 (2개)

1. `안 사면 후회함`
2. `지금 사기엔 좀...`

### 4라벨 잔존 검색 (`단기 주목` | `관망`)

| 영역 | 결과 |
|---|---|
| `agents/label_rules.py` | **의도적** 레거시 매핑 테이블만 유지 |
| `main.py` | 모멘텀 **태그** 문자열 `"관망"` (라벨 아님, 중립 태그) |
| `template/kr_market/template.html` / `index.html` | **없음** — 배지는 2라벨만 |
| `template/kr_market/preview.html` | 더미 프리뷰에 `"관망 추천"` 잔존 (프로덕션 경로 아님) |
| `reports/templates/_report_core.html`, `recommender.py`, `risk.py` | 구 HTML 리포트·에이전트 프롬프트 문구 (KR kr_market 미사용) |
| `08_KR_REPORT_FINAL_RESULT.md`, `06_CURSOR_IMPLEMENTATION_TASK.md` | 과거 문서 기록 |

**결론**: kr_market MVP UI·투표 파이프라인에서는 **최종 라벨 2개만** 사용. 4라벨 이름은 `normalize_label()` 호환용·구 리포트·문서에만 남음.

---

## 4. 종목별 AI 투표 루프 결과

### 호출 구조

```
build_stock_label_votes(ticker, name, stock, pipeline)
  ├─ api_vote_deepseek  → deepseek-v4-pro  (실패/키 없음 → rules_vote_deepseek)
  ├─ api_vote_grok      → grok-4.3         (실패/키 없음 → rules_vote_grok)
  └─ api_vote_gemini    → gemini-3.1-pro-preview (실패/키 없음 → rules_vote_gemini)
       └─ resolve_final_label() → final_label + label_reason (최대 2줄)
```

- 구현 파일: `agents/label_vote_api.py`, `agents/label_vote_rules.py`, `agents/label_voting.py`
- 투표 레코드: `engine`, `model`, `label`, `reason`, `confidence`, `source` (`api` | `rules`)

### Fallback

| 조건 | 동작 |
|---|---|
| `DEEPSEEK_API_KEY` 없음 | `rules_vote_deepseek` |
| `GROK_API_KEY` 없음 | `rules_vote_grok` |
| `GEMINI_API_KEY` 없음 | `rules_vote_gemini` |
| API 응답 파싱 실패 | 동일 엔진 rules fallback |

API와 rules는 **함수 단위로 분리**되어 있으며, 결과에 `source`·`model`이 항상 기록됨.

### 모델명 저장

- `ai_votes[]` 각 항목에 `model` 필드 저장 (`main` → `report_data.stock_analysis[].ai_votes` → `reportData.aiVotes`).

### UI 표시

- 카드: **최종 라벨 배지 + 2줄 이유**만 (`opinion` / `ui_comment` 필터).
- 엔진별 투표 목록: 템플릿에서 **제거** (상세는 `window.reportData.aiVotes`).

---

## 5. `reportData` JS 객체 결과

### 생성 위치

- `template/kr_market/report_adapter.py` → `build_report_data_js()`
- `build_kr_market_context()`에서 `report_data_json`으로 JSON 직렬화
- `template/kr_market/template.html` 하단:

```html
<script>
  window.reportData = { ... };
</script>
```

### 포함 필드

```javascript
window.reportData = {
  market: { type, meta, commentary, commentary_source, indices },
  sectors: { [sector_key]: { name, is_inflow, flow_amount, commentary, ... } },
  stocks: [{ ticker, name, sector_key, label, reason, verdict_class }],
  aiVotes: [{ ticker, model, engine, label, reason, confidence, source }],
  meta: { market_type, labels, generated_at, indices, sectors, pipeline_engines }
}
```

- 없는 값: `N/A` 또는 빈 객체/배열
- `meta.labels`: 2라벨 배열만

### `index.html`에서 확인 방법

1. 브라우저로 `template/kr_market/index.html` 열기
2. 개발자 도구 콘솔: `window.reportData`
3. 샘플 렌더: `python template/kr_market/render.py`
4. 실데이터: `python template/kr_market/build_index.py` 또는 `python main.py us_close_kr_before` (국장 타입 시 kr_market 렌더 경로)

---

## 6. `stock_votes.py` 정리 결과

| 항목 | 내용 |
|---|---|
| 처리 | **삭제하지 않음** — 상단 `DeprecationWarning` + docstring |
| `main` / `report_adapter` | `stock_votes` **import 없음** (`label_vote_helpers` / `label_voting` 사용) |
| 역할 | 구 5인 분석가(매수/홀드/매도) HTML 리포트용 레거시 |
| KR MVP | **`label_voting.py` 중심으로 통일** |

---

## 7. 아직 남은 문제·추후 작업

| 항목 | 설명 |
|---|---|
| 이중 리포트 출력 | `reports/templates/*.html`(구 PDF) vs `template/kr_market/index.html` — 08과 동일, 통합 미착수 |
| 내부 에이전트 verdict | `supply_demand`, `momentum`, `risk` 등은 여전히 매수/홀드/매도 → rules 투표 입력으로만 사용 |
| `preview.html` | 더미 4라벨/관망 문구 잔존 (선택 정리) |
| `main._momentum_tags` | 태그 텍스트 `"관망"`은 라벨이 아닌 중립 태그 |
| API 검증 | 키·네트워크·KRX/pykrx 지연은 환경 의존; 무키 환경은 rules만 수동 확인 권장 |
| 미장 | **이번 작업 범위 외** — KR/US 구조는 `market_type` 등으로 확장 가능하게 유지 |

---

## 8. 검증 요약

| 검증 | 결과 |
|---|---|
| `python template/kr_market/render.py` | `index.html` 생성 OK |
| `index.html` 2라벨 배지 | `안 사면 후회함`, `지금 사기엔 좀...` 확인 |
| `window.reportData` | 스크립트 블록 존재, `labels` 2개 |
| `build_stock_label_votes` (API 키 있음) | 3엔진 `source: api` 확인 |
| `stock_votes` import | 코드베이스 **0건** (KR 경로) |

---

*08 보고서의 부분성공 항목 중 **라벨 정책·AI 투표·reportData·레거시 정리**는 본 작업으로 반영 완료. 데이터 파이프라인·구 templates 통합은 추후 이슈.*
