# AI 모델 사용 정책

판단/투표는 유료·상위 모델을 사용하고, 단순 문장 축약은 무료 또는 저비용 모델을 사용한다.

## 모델 배치

| 단계 | 엔진 | 모델 | 비용 정책 | 역할 |
|---|---|---|---|---|
| 초안 분석 | DeepSeek | `deepseek-v4-flash` | 유료/저비용 | 데이터 요약, 리포트 초안 |
| 핵심 분석 투표 | DeepSeek | `deepseek-v4-pro` | 유료/상위 | 데이터 기반 종목 판단 |
| 시장 반응 투표 | Grok | `grok-4.3` | 유료/상위 | X/커뮤니티/과열감 판단 |
| 리스크 투표 | Gemini | `gemini-3.1-pro-preview` | 유료/상위 | 보수적 리스크 판단 |
| 2줄 축약 | Gemini | `gemini-3.1-flash-lite-preview` | 무료/저비용 후보 | 문장 압축, 톤 정리 |
| 축약 fallback | Gemini | `gemini-2.5-flash-lite` | 저비용 후보 | 2줄 축약 fallback |

## 투표 단계 고정 모델

```txt
DeepSeek · deepseek-v4-pro
Grok · grok-4.3
Gemini · gemini-3.1-pro-preview
```

## 2줄 축약 모델

```txt
Gemini · gemini-3.1-flash-lite-preview
```

단, 실제 API 사용 가능 여부에 따라 `.env`에서 교체 가능하게 만든다.

```env
DEEPSEEK_DRAFT_MODEL=deepseek-v4-flash
DEEPSEEK_VOTE_MODEL=deepseek-v4-pro
GROK_VOTE_MODEL=grok-4.3
GEMINI_RISK_MODEL=gemini-3.1-pro-preview
GEMINI_SUMMARY_MODEL=gemini-3.1-flash-lite-preview
GEMINI_SUMMARY_FALLBACK_MODEL=gemini-2.5-flash-lite
```

## 운영 원칙

```txt
중요한 결정 = 유료/상위 모델
화면 문장 축약 = 무료/저비용 모델
```
