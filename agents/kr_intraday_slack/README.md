# KR 장중 슬랙 스캔

설계 문서: `docs/ai_stock_slack_logic_v2/ai_stock_slack_logic_v2/`

## 실행

```bash
# 더미
python scripts/run_kr_intraday_slack.py --slot 0930

# 라이브 1종목 테스트
python scripts/test_live_watchlist_data.py --ticker 089030

# 라이브 25종목
python scripts/test_live_watchlist_data.py --all

# 라이브 드라이런
python scripts/run_kr_intraday_slack.py --slot 0930 --live

# 운영 발송 (로컬)
python scripts/run_kr_intraday_slack.py --slot 1050 --live --send

# GitHub Actions: `.github/workflows/kr_intraday_slack.yml` — KST 09:30/10:50/13:50/14:50 자동 --live --send
```

## AI (멀티 모델)

### DeepSeek — 1차 판단 (필수)

```env
AI_PROVIDER=deepseek
AI_MODEL=deepseek-chat
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

- 규칙 1차 후보(최대 7) → DeepSeek JSON 배치 → `ai_send_slack=true` 만 메시지 후보
- LLM 실패/파싱 실패 시 **더미 판단 없음**, 슬랙 미발송
- 슬랙 발송 최종 조건: DeepSeek `ai_send_slack` + 허용 decision + SendFilter

### Grok — 뉴스/X 보조 (optional)

```env
AI_SOCIAL_PROVIDER=grok
AI_SOCIAL_MODEL=grok-3
GROK_API_KEY=
```

- `ai_send_slack=true` 종목만 호출
- 발송 여부·decision 변경 없음, 메시지 `판단` 섹션에 맥락만 보완
- 키 없음/실패 → 로그만 남기고 skip

### Gemini — 슬랙 문장 정리 (optional)

```env
AI_SUMMARY_PROVIDER=gemini
AI_SUMMARY_MODEL=gemini-1.5-flash
GEMINI_API_KEY=
```

- DeepSeek 초안 → Gemini polish, 실패 시 초안 그대로
- 키 없음/실패 → 로그만 남기고 skip

### 드라이런

- `--send` 없으면 슬랙 미발송; Grok/Gemini도 키 없으면 skip

```bash
python scripts/run_kr_intraday_slack.py --slot 0930 --live
python scripts/run_kr_intraday_slack.py --slot 0930 --live --send
```

## 파이프라인

`MarketDataAgent` → `SectorMoodAgent` → `WatchlistPickAgent` → `EntryPriceAgent` → `SendFilterAgent` → `SlackMessageAgent`

## 로그

`data/logs/kr_slack/YYYY-MM-DD.jsonl`
