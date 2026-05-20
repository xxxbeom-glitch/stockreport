# AI 투표 및 라벨 규칙 (KR MVP — 2라벨)

## AI 투표자

| 투표자 | 실제 모델 | 판단 역할 |
|---|---|---|
| DeepSeek | `deepseek-v4-pro` | 데이터 기반 분석 |
| Grok | `grok-4.3` | 시장 반응·과열감 |
| Gemini | `gemini-3.1-pro-preview` | 리스크·보수적 최종 검수 |

구현: `agents/label_vote_api.py` (API) → 실패 시 `agents/label_vote_rules.py` (rules).

## 투표 출력 JSON

```json
{
  "engine": "DeepSeek",
  "model": "deepseek-v4-pro",
  "label": "안 사면 후회함",
  "reason": "외국인 순매수·거래량 동반.",
  "confidence": 72,
  "source": "api"
}
```

`source`: `api` | `rules`

## 최종 라벨 (2개만)

1. **안 사면 후회함** — 수급·재료가 우호적이나 직접 매수 권유 문구 금지
2. **지금 사기엔 좀...** — 과열·리스크·타이밍 부담

레거시 `단기 주목` / `관망` / 매수·홀드·매도는 `agents/label_rules.normalize_label()`에서 위 2개로 매핑.

## 최종 라벨 결정

`agents/label_voting.resolve_final_label()`:

- 2표 이상 `지금 사기엔 좀...` → 최종 동일
- 2표 이상 `안 사면 후회함` → 최종 동일
- 그 외 Gemini 라벨로 tie-break

## UI·코멘트

- 화면: 최종 라벨 + 이유 최대 2줄 (`utils/ui_comment`, 메모형, 입니다/합니다 금지)
- 상세 투표: `window.reportData.aiVotes` (디버그·확장용)

## 레거시

- `agents/stock_votes.py`: 5인 분석가(매수/홀드/매도) — **deprecated**, kr_market 미사용
