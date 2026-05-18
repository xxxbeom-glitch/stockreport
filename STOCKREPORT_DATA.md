# 데이터 소스 & 섹터 흐름 설계

> **작업 경로:** `D:\project\stockreport`  
> **목적:** 어느 섹터로 돈이 흐르고 빠지는지 자동 감지

---

## 목차

1. [데이터 소스 전체 구성](#1-데이터-소스-전체-구성)
2. [섹터 흐름 감지 모듈](#2-섹터-흐름-감지-모듈)
3. [동적 종목 발굴 로직](#3-동적-종목-발굴-로직)
4. [관심 섹터 & 종목 목록](#4-관심-섹터--종목-목록)
5. [config.py 최종본](#5-configpy-최종본)
6. [data/ 모듈 전체 코드](#6-data-모듈-전체-코드)
7. [추후 추가 예정 API](#7-추후-추가-예정-api)

---

## 1. 데이터 소스 전체 구성

### 현재 사용 가능 (키 없음 or 이미 발급)

| 소스 | 용도 | 키 필요 | 비용 |
|------|------|---------|------|
| **yfinance** | 미국 섹터 ETF·지수·거래량 | 없음 | 무료 |
| **pykrx** | 한국 수급·지수·거래량·시총 | 없음 | 무료 |
| **Grok 4.3** | X 실시간 뉴스·이슈 | ✅ 발급 완료 | 유료 |
| **Gemini 2.5 Pro** | 분석·종합 | ✅ 발급 완료 | 유료 |
| **Slack Webhook** | 리포트 발송 | ✅ 발급 완료 | 무료 |
| **Firebase** | 데이터 저장·2주 보관 | ✅ 설정 완료 | 무료 |

### 추후 추가 예정

| 소스 | 용도 | 상태 |
|------|------|------|
| **KIS API (한국투자증권)** | 실시간 수급·호가 | 내일 계좌 개설 |
| **eBest API** | 재무·컨센서스·목표주가 | 계좌 개설 예정 |

---

## 2. 섹터 흐름 감지 모듈

### 미국 섹터 흐름 — SPDR ETF 11개 스캔

```
기술       XLK   반도체·소프트웨어
산업재     XLI   방산·항공·기계
에너지     XLE
금융       XLF
헬스케어   XLV
소재       XLB
유틸리티   XLU   전력·AI 인프라 수혜
부동산     XLRE
필수소비   XLP
임의소비   XLY
통신       XLC
```

**AI 특화 섹터 ETF 추가 스캔**

```
반도체     SMH   NVDA·AMD·AVGO 집중
빅테크     QQQ
방산       ITA
클라우드   SKYY
AI인프라   BOTZ
```

### 섹터 온도 판정 기준

```
🔥 뜨거움   5일 수익률 +2% 이상 + 거래량 1.3배 이상
🟡 따뜻함   5일 수익률 +0.5% ~ +2%
⚪ 보합     -0.5% ~ +0.5%
🔵 차가움   -2% 이하
```

---

## 3. 동적 종목 발굴 로직

고정 리스트 없이 매일 시장에서 직접 발굴.

```
오늘의 분석 대상 =
  코스피 거래량 급등 상위 20개
  + 코스닥 거래량 급등 상위 20개
  + 외국인 순매수 상위 20개
  + 핵심 고정 종목 (삼전·하이닉스 등 5개)
  → 중복 제거 → 최종 30~40개 분석
```

**평균 대비 거래량 배율 기준**

```
2배 이상   강한 신호 — 반드시 분석
1.5배      주의 종목 — 포함
1배 이하   제외
```

---

## 4. 관심 섹터 & 종목 목록

### AI 반도체·소부장 (코스닥 중심)

| 종목명 | 코드 | 역할 |
|--------|------|------|
| 한미반도체 | 042700 | HBM 본딩 장비, NVDA 직접 수혜 |
| 리노공업 | 058470 | AI 테스트 소켓 독점 |
| HPSP | 403870 | 고압 수소 어닐링 장비 |
| 주성엔지니어링 | 036930 | 반도체 증착 장비 |
| 원익IPS | 240810 | 반도체 장비 |
| 이오테크닉스 | 039030 | 레이저 어닐링 |
| 피에스케이홀딩스 | 460850 | 반도체 전공정 장비 |
| ISC | 095340 | 반도체 테스트 소켓 |

### AI 반도체 대형주 (코스피)

| 종목명 | 코드 | 역할 |
|--------|------|------|
| 삼성전자 | 005930 | HBM·파운드리 |
| SK하이닉스 | 000660 | HBM 세계 1위 |

### AI 전력·데이터센터 (코스피)

| 종목명 | 코드 | 역할 |
|--------|------|------|
| LS일렉트릭 | 010120 | 데이터센터 전력 국내 1위, xAI 납품 |
| 효성중공업 | 298040 | 초고압 변압기, 수주 급증 |
| HD현대일렉트릭 | 267260 | 변압기·전력기기 |
| 산일전기 | 062040 | 데이터센터 특수변압기 |
| 두산에너빌리티 | 034020 | 원전·가스터빈 |

### 방산 (코스피)

| 종목명 | 코드 | 역할 |
|--------|------|------|
| 한화에어로스페이스 | 012450 | K9 자주포·미사일 수출 |
| LIG넥스원 | 079550 | 유도무기 |
| 현대로템 | 064350 | K2 전차 |
| 풍산 | 103140 | 155mm 포탄 |

### 조선·해양방산 (코스피)

| 종목명 | 코드 | 역할 |
|--------|------|------|
| HD한국조선해양 | 009540 | LNG선·방산함정 지주사 |
| 한화오션 | 042660 | 잠수함·무인수상정·LNG선 |
| 삼성중공업 | 010140 | LNG선·드릴십 |
| HD현대미포 | 010620 | 중소형 선박 |

### 자동차 (코스피)

| 종목명 | 코드 | 역할 |
|--------|------|------|
| 현대차 | 005380 | 완성차 |
| 기아 | 000270 | 완성차 |
| 현대모비스 | 012330 | 핵심 부품 |

---

## 5. config.py 최종본

`D:\project\stockreport\config.py`:

```python
import os
from dotenv import load_dotenv

load_dotenv()

# ── API 키 ────────────────────────────────────────────────
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
GROK_API_KEY    = os.getenv("GROK_API_KEY")
SLACK_WEBHOOK   = os.getenv("SLACK_WEBHOOK_URL")
FIREBASE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET")
FIREBASE_KEY    = os.getenv("FIREBASE_KEY_PATH",
                  "cole-c3f96-firebase-adminsdk-fbsvc-be477d7ab7.json")

# 추후 추가 예정
KIS_APP_KEY     = os.getenv("KIS_APP_KEY")       # 내일 추가
KIS_APP_SECRET  = os.getenv("KIS_APP_SECRET")    # 내일 추가
EBEST_APP_KEY   = os.getenv("EBEST_APP_KEY")     # 추후 추가
EBEST_APP_SECRET= os.getenv("EBEST_APP_SECRET")  # 추후 추가

# ── AI 모델 ───────────────────────────────────────────────
GEMINI_PRO    = "gemini-2.5-pro"
GEMINI_FLASH  = "gemini-2.5-flash"
GROK_MODEL    = "grok-4.3"
GROK_BASE_URL = "https://api.x.ai/v1"

# ── 미국 섹터 ETF (SPDR 11개 + AI 특화) ──────────────────
US_SECTOR_ETFS = {
    # SPDR 섹터 11개
    "기술":    "XLK",
    "산업재":  "XLI",
    "에너지":  "XLE",
    "금융":    "XLF",
    "헬스케어":"XLV",
    "소재":    "XLB",
    "유틸리티":"XLU",
    "부동산":  "XLRE",
    "필수소비":"XLP",
    "임의소비":"XLY",
    "통신":    "XLC",
    # AI 특화
    "반도체":  "SMH",
    "빅테크":  "QQQ",
    "방산":    "ITA",
    "클라우드":"SKYY",
}

# ── 국내 ETF 매핑 (미국 테마 → 국내 접근) ────────────────
KR_ETF_MAP = {
    "반도체":    {"name": "TIGER 미국필라델피아반도체나스닥", "code": "381180"},
    "빅테크":    {"name": "KODEX 미국나스닥100",              "code": "379800"},
    "방산":      {"name": "TIGER 미국S&P500방산",             "code": "455870"},
    "에너지":    {"name": "TIGER 미국S&P500에너지",           "code": "441640"},
    "바이오":    {"name": "KODEX 미국바이오",                  "code": "203780"},
    "클라우드":  {"name": "TIGER 글로벌클라우드컴퓨팅INDXX",  "code": "371460"},
    "AI인프라":  {"name": "TIGER AI반도체핵심장비",            "code": "455860"},
}

# ── 선행지표 티커 ─────────────────────────────────────────
INDICATORS = {
    "달러인덱스": "DX-Y.NYB",
    "미국채10년": "^TNX",
    "WTI유가":    "CL=F",
    "금":         "GC=F",
    "구리":       "HG=F",
    "VIX":        "^VIX",
    "원달러":     "KRW=X",
}

# ── 핵심 고정 종목 (항상 포함) ────────────────────────────
CORE_TICKERS = {
    "삼성전자":   "005930",
    "SK하이닉스": "000660",
    "현대차":     "005380",
    "기아":       "000270",
    "LS일렉트릭": "010120",
}

# ── 관심 섹터별 종목 (동적 발굴 보조) ────────────────────
KR_SECTORS = {
    "AI반도체소부장": {
        "market": "KOSDAQ",
        "tickers": {
            "한미반도체":      "042700",
            "리노공업":        "058470",
            "HPSP":            "403870",
            "주성엔지니어링":  "036930",
            "원익IPS":         "240810",
            "이오테크닉스":    "039030",
            "피에스케이홀딩스":"460850",
            "ISC":             "095340",
        }
    },
    "AI전력": {
        "market": "KOSPI",
        "tickers": {
            "LS일렉트릭":     "010120",
            "효성중공업":     "298040",
            "HD현대일렉트릭": "267260",
            "산일전기":       "062040",
            "두산에너빌리티": "034020",
        }
    },
    "방산": {
        "market": "KOSPI",
        "tickers": {
            "한화에어로스페이스": "012450",
            "LIG넥스원":          "079550",
            "현대로템":            "064350",
            "풍산":                "103140",
        }
    },
    "조선해양방산": {
        "market": "KOSPI",
        "tickers": {
            "HD한국조선해양": "009540",
            "한화오션":        "042660",
            "삼성중공업":      "010140",
            "HD현대미포":      "010620",
        }
    },
    "자동차": {
        "market": "KOSPI",
        "tickers": {
            "현대차":     "005380",
            "기아":       "000270",
            "현대모비스": "012330",
        }
    },
}

# ── 보관 기간 ─────────────────────────────────────────────
RETENTION_DAYS = 14
```

---

## 6. data/ 모듈 전체 코드

### data/us_market.py

```python
import yfinance as yf
from config import US_SECTOR_ETFS, INDICATORS
from datetime import datetime, timedelta

def get_sector_temperature():
    """
    미국 섹터 ETF 11개 + AI 특화 스캔
    → 어디로 돈이 들어오고 빠지는지 온도로 표현
    """
    results = {}
    for sector, ticker in US_SECTOR_ETFS.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if len(hist) < 2:
                continue

            # 5일 수익률
            ret_5d    = (hist.iloc[-1]['Close'] - hist.iloc[0]['Close']) \
                        / hist.iloc[0]['Close'] * 100

            # 오늘 거래량 vs 5일 평균
            avg_vol   = hist['Volume'].mean()
            vol_ratio = hist.iloc[-1]['Volume'] / avg_vol if avg_vol else 1

            # 온도 판정
            if ret_5d > 2 and vol_ratio > 1.3:
                temp = "뜨거움"
            elif ret_5d > 0.5:
                temp = "따뜻함"
            elif ret_5d < -2:
                temp = "차가움"
            else:
                temp = "보합"

            results[sector] = {
                "ticker":    ticker,
                "temp":      temp,
                "ret_5d":    round(ret_5d, 2),
                "vol_ratio": round(vol_ratio, 1),
                "flow":      "유입" if ret_5d > 0 else "유출",
            }
        except Exception:
            continue

    # 뜨거운 순서로 정렬
    return dict(sorted(
        results.items(),
        key=lambda x: x[1]['ret_5d'],
        reverse=True
    ))

def get_us_indices():
    """미국 주요 지수"""
    indices = {
        "나스닥":   "^IXIC",
        "S&P500":   "^GSPC",
        "다우":     "^DJI",
        "VIX":      "^VIX",
    }
    results = {}
    for name, ticker in indices.items():
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if len(hist) >= 2:
                today  = hist.iloc[-1]['Close']
                prev   = hist.iloc[-2]['Close']
                change = (today - prev) / prev * 100
                results[name] = {
                    "value":  round(today, 2),
                    "change": round(change, 2),
                }
        except Exception:
            continue
    return results

def get_indicators():
    """선행지표 — 달러·금리·유가·VIX·원달러"""
    results = {}
    for name, ticker in INDICATORS.items():
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if len(hist) >= 2:
                today  = hist.iloc[-1]['Close']
                prev   = hist.iloc[-2]['Close']
                change = (today - prev) / prev * 100
                results[name] = {
                    "value":  round(today, 2),
                    "change": round(change, 2),
                }
        except Exception:
            continue
    return results

def get_top_volume_stocks(tickers: list):
    """미국 거래량 급등 종목 — 평균 대비 배율"""
    results = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist  = stock.history(period="2d")
            info  = stock.info
            if len(hist) < 2:
                continue
            today, prev = hist.iloc[-1], hist.iloc[-2]
            avg_vol   = info.get('averageVolume', 1)
            change    = (today['Close'] - prev['Close']) / prev['Close'] * 100
            vol_ratio = today['Volume'] / avg_vol if avg_vol else 1
            results.append({
                "ticker":   ticker,
                "name":     info.get('shortName', ticker),
                "change":   round(change, 2),
                "volume_x": round(vol_ratio, 1),
                "price":    round(today['Close'], 2),
            })
        except Exception:
            continue
    return sorted(results, key=lambda x: x['volume_x'], reverse=True)[:5]
```

### data/kr_market.py

```python
from pykrx import stock
from datetime import datetime, timedelta
from config import CORE_TICKERS

def _trading_date():
    """최근 영업일 반환"""
    d = datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

def _prev_date(days=5):
    d = datetime.now() - timedelta(days=days)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

def get_kr_indices():
    """코스피·코스닥 지수"""
    today = _trading_date()
    prev  = _prev_date()
    results = {}
    for name, ticker in [("코스피", "1001"), ("코스닥", "2001")]:
        try:
            df = stock.get_index_ohlcv(prev, today, ticker)
            if len(df) >= 2:
                results[name] = {
                    "value":  int(df.iloc[-1]['종가']),
                    "change": round(df.iloc[-1]['등락률'], 2),
                }
        except Exception:
            continue
    return results

def get_sector_flow_kr():
    """
    한국 섹터별 자금 흐름
    KRX 업종 지수 기반
    """
    today = _trading_date()
    prev  = _prev_date()

    kr_sector_indices = {
        "반도체·IT":  "1028",
        "자동차":      "1007",
        "조선":        "1013",
        "철강·금속":   "1010",
        "화학":        "1011",
        "건설":        "1006",
        "금융":        "1005",
        "바이오":      "1027",
    }
    results = {}
    for name, idx in kr_sector_indices.items():
        try:
            df = stock.get_index_ohlcv(prev, today, idx)
            if len(df) >= 2:
                ret = (df.iloc[-1]['종가'] - df.iloc[0]['종가']) \
                      / df.iloc[0]['종가'] * 100
                results[name] = {
                    "ret_5d": round(ret, 2),
                    "flow":   "유입" if ret > 0 else "유출",
                    "temp":   "뜨거움" if ret > 2 else
                              ("따뜻함" if ret > 0.5 else
                              ("차가움" if ret < -2 else "보합")),
                }
        except Exception:
            continue
    return dict(sorted(
        results.items(),
        key=lambda x: x[1]['ret_5d'],
        reverse=True
    ))

def get_foreign_flow():
    """외국인 순매수 상위 종목"""
    today = _trading_date()
    try:
        df = stock.get_market_trading_value_by_ticker(today, market="KOSPI")
        df = df.sort_values("외국인", ascending=False)
        results = []
        for ticker in df.head(10).index:
            try:
                name  = stock.get_market_ticker_name(ticker)
                value = df.loc[ticker, "외국인"]
                results.append({
                    "ticker": ticker,
                    "name":   name,
                    "value":  f"{int(value/1e8)}억",
                    "flow":   "순매수" if value > 0 else "순매도",
                    "is_buy": value > 0,
                })
            except Exception:
                continue
        return results
    except Exception:
        return []

def get_dynamic_targets():
    """
    오늘 시장에서 수급 몰리는 종목 동적 발굴
    고정 리스트 없이 매일 새로 추출
    """
    today = _trading_date()

    # 코스피 거래량 급등
    try:
        kospi_df = stock.get_market_ohlcv(today, market="KOSPI")
        kospi_df['배율'] = kospi_df['거래량'] / kospi_df['거래량'].mean()
        kospi_top = kospi_df[kospi_df['배율'] >= 1.5]\
                    .sort_values('배율', ascending=False)\
                    .head(20).index.tolist()
    except Exception:
        kospi_top = []

    # 코스닥 거래량 급등
    try:
        kosdaq_df = stock.get_market_ohlcv(today, market="KOSDAQ")
        kosdaq_df['배율'] = kosdaq_df['거래량'] / kosdaq_df['거래량'].mean()
        kosdaq_top = kosdaq_df[kosdaq_df['배율'] >= 1.5]\
                     .sort_values('배율', ascending=False)\
                     .head(20).index.tolist()
    except Exception:
        kosdaq_top = []

    # 외국인 순매수 상위
    try:
        flow_df = stock.get_market_trading_value_by_ticker(
            today, market="KOSPI"
        )
        foreign_top = flow_df.sort_values("외국인", ascending=False)\
                              .head(20).index.tolist()
    except Exception:
        foreign_top = []

    # 핵심 고정 종목 항상 포함
    core = list(CORE_TICKERS.values())

    # 전체 합치기 + 중복 제거
    all_tickers = list(set(
        kospi_top + kosdaq_top + foreign_top + core
    ))

    # 종목명 매핑
    results = []
    for ticker in all_tickers:
        try:
            name = stock.get_market_ticker_name(ticker)
            results.append({"ticker": ticker, "name": name})
        except Exception:
            continue

    return results

def get_volume_leaders(market="KOSPI", top=5):
    """거래량 급등 종목 상위 N개"""
    today = _trading_date()
    try:
        df = stock.get_market_ohlcv(today, market=market)
        df['배율'] = df['거래량'] / df['거래량'].mean()
        df = df.sort_values('배율', ascending=False)
        results = []
        for ticker in df.head(top*2).index:
            try:
                name = stock.get_market_ticker_name(ticker)
                row  = df.loc[ticker]
                results.append({
                    "ticker":   ticker,
                    "name":     name,
                    "change":   round(row.get('등락률', 0), 2),
                    "volume_x": round(row['배율'], 1),
                    "is_up":    row.get('등락률', 0) > 0,
                })
            except Exception:
                continue
            if len(results) >= top:
                break
        return results
    except Exception:
        return []
```

### data/grok_realtime.py

```python
from openai import OpenAI
from config import GROK_API_KEY, GROK_BASE_URL, GROK_MODEL

client = OpenAI(api_key=GROK_API_KEY, base_url=GROK_BASE_URL)

def get_sector_buzz() -> str:
    """X에서 지금 어느 섹터·종목이 가장 화제인지"""
    prompt = """
    지금 X(트위터)에서 미국·한국 주식 관련으로
    가장 많이 언급되는 섹터와 종목 TOP 5를 알려줘.
    각각: 섹터/종목명 / 이유 한 줄 / 긍정·부정·중립
    한국어로 답해.
    """
    res = client.chat.completions.create(
        model=GROK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
    )
    return res.choices[0].message.content

def get_premarket_movers() -> str:
    """미국 프리마켓 급등 종목"""
    prompt = """
    지금 미국 프리마켓에서 가장 많이 움직이는 종목과
    이유를 X 및 실시간 뉴스 기반으로 알려줘.
    종목명 / 방향 / 이유 간략히. 한국어로.
    """
    res = client.chat.completions.create(
        model=GROK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
    )
    return res.choices[0].message.content

def get_kr_market_buzz() -> str:
    """한국 장 관련 실시간 이슈"""
    prompt = """
    오늘 한국 주식시장 관련해서
    X와 뉴스에서 가장 화제인 내용 3가지를 알려줘.
    한국어로 간략하게.
    """
    res = client.chat.completions.create(
        model=GROK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
    )
    return res.choices[0].message.content
```

---

## 7. 추후 추가 예정 API

### KIS API 추가 시 (내일)

```
1. apiportal.koreainvestment.com 접속
2. 로그인 → API 신청 → APP KEY·SECRET 발급
3. GitHub Secrets 추가:
   KIS_APP_KEY
   KIS_APP_SECRET
4. .env 추가:
   KIS_APP_KEY=발급받은키
   KIS_APP_SECRET=발급받은시크릿
5. data/kis_market.py 파일 추가 예정
   → 섹터별 외국인·기관 실시간 수급
   → 공매도 잔고
   → 실시간 호가
```

### eBest API 추가 시

```
1. openapi.ls-sec.co.kr 접속
2. 계좌 개설 → APP KEY 발급
3. GitHub Secrets 추가:
   EBEST_APP_KEY
   EBEST_APP_SECRET
4. data/ebest_market.py 파일 추가 예정
   → 재무데이터 (PER·PBR·ROE)
   → 애널리스트 컨센서스
   → 목표주가
```

---

## GitHub Secrets 현재 상태

```
✅ GEMINI_API_KEY
✅ GROK_API_KEY
✅ SLACK_WEBHOOK_URL
✅ FIREBASE_SERVICE_ACCOUNT
✅ FIREBASE_STORAGE_BUCKET
⬜ KIS_APP_KEY           내일 추가
⬜ KIS_APP_SECRET        내일 추가
⬜ EBEST_APP_KEY         추후 추가
⬜ EBEST_APP_SECRET      추후 추가
```

---

*D:\project\stockreport — Data Sources v1.0*
