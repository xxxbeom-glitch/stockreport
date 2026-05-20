# kr_market 모바일 HTML (Figma 기준)

Figma: [제목 없음 · node 6-142](https://www.figma.com/design/CxxvVJfcOcZX6gEHjEp8Vb/%EC%A0%9C%EB%AA%A9-%EC%97%86%EC%9D%8C?node-id=6-142&m=dev)

## 파일

| 파일 | 용도 |
|------|------|
| `index.html` | Figma 목업과 동일 레이아웃 **정적 미리보기** (브라우저에서 바로 열기) |
| `template.html` | Jinja2 템플릿 (파이프라인 데이터 바인딩) |
| `styles.css` | 공통 스타일 |
| `sample_data.json` | 렌더 예시 JSON |
| `render.py` | `sample_data.json` → `preview.html` 생성 |

## 미리보기 (현재: 전부 더미)

- 텍스트·숫자: `(더미)` placeholder
- 종목 로고: **36×36px** 회색 SVG 플레이스홀더 (Figma 크기)

```bash
# 정적 목업
start template/kr_market/index.html

# JSON으로 렌더
python template/kr_market/render.py
# → preview.html
```

## 당신이 제공하면 좋은 것

### 필수 (콘텐츠)

1. **헤더**
   - `market_line`: 예) `한국시장 | 2026-05-20 수요일 09:00 업데이트`

2. **마켓 주요 지표** (`indices` + `market_commentary`)
   - 코스피 / 코스닥 / 달러·원 환율: 값, 등락률, 상승·하락 여부
   - Gemini 매크로 코멘트 2~3문장 (`market_commentary`)

3. **섹터 유입·유출** (`sectors[]`)
   - 섹터명, 유입·유출 금액(억원), 상승 종목 리스트
   - 섹터별 AI 코멘트 (`commentary`)
   - (선택) 섹터 필터 옵션 목록

4. **관심 종목** (`stocks[]`)
   - 종목명, 투자의견 배지 문구 (예: `안사면 후회함`, `지금 사기엔 좀…`)
   - 최종 투자의견 3문장 (`opinion`) — recommender / 에이전트 종합
   - 표 행: 현재가, 목표가, 외국인 순매수, 52주 최고가
   - 회사 한줄 요약 (`company_summary`) — Gemini company_report 등

### 선택 (디자인·품질)

| 항목 | 설명 |
|------|------|
| 종목 로고 URL | `logo_url` (없으면 `logo_text` 2글자 표시) |
| 목표가 출처 | 애널리스트 목표가 / 내부 산식 중 무엇인지 |
| 배지 문구 규칙 | 매수·홀드·매도별 고정 문구 목록 |
| Figma 에셋 | 아이콘·로고 SVG/PNG export 경로 |
| 폰트 | 현재 Pretendard CDN (오프라인이면 `reports/static/Pretendard` 사용) |

### 파이프라인 연동 시 (코드 쪽)

`main.py` / `reports/pdf_generator.py`에서 `template/kr_market/template.html`을 렌더하도록 연결하면 됩니다.  
`sample_data.json` 필드명을 그대로 `_build_report_data()` 결과에 매핑하면 됩니다.

## `sample_data.json` 스키마 요약

```json
{
  "title": "투자 인사이트",
  "market_line": "한국시장 | ...",
  "indices": [{"label": "코스피", "value": "...", "change": "+2.66%", "is_up": true}],
  "market_commentary": "3문장",
  "sectors": [{"name": "...", "flow_amount": "+1300억원", "is_inflow": true, "tag": "...", "stock_names": [], "commentary": "..."}],
  "stocks": [{"name": "...", "verdict_badge": "...", "verdict_class": "buy|hold|sell", "opinion": "...", "metrics": [{"label": "현재가", "value": "..."}], "company_summary": "..."}]
}
```

## Figma와의 차이 (현재)

- 드롭다운(`전체섹터`)은 UI만 있고 **필터 동작 JS는 없음** (필요 시 추가)
- 에이전트 5명 테이블은 이 Figma 화면에 없어 **종목 카드 1개 의견**만 표시
- 탭 네비게이션 없음 (Figma 단일 스크롤 화면 기준)
