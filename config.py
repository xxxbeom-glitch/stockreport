"""Central configuration for stock report data pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

load_dotenv()


def legacy_report_slack_enabled() -> bool:
    """장시작/장마감 브리핑 등 예전 리포트 Slack. 기본 OFF — 장중 알림만 허용."""
    return os.getenv("STOCKREPORT_ALLOW_LEGACY_REPORT_SLACK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


# ---- Paths ----
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent

# ---- API keys / endpoints ----
GEMINI_API_KEY: Final[str] = os.getenv("GEMINI_API_KEY", "")
GROK_API_KEY: Final[str] = os.getenv("GROK_API_KEY", "")
SLACK_BOT_TOKEN: Final[str] = os.getenv("SLACK_BOT_TOKEN", "")
# 실사용 알림 (채널 ID 또는 Incoming Webhook URL)
SLACK_BUY_CANDIDATE_WEBHOOK: Final[str] = os.getenv("SLACK_BUY_CANDIDATE_WEBHOOK", "")
SLACK_BUY_CANDIDATE_CHANNEL: Final[str] = os.getenv("SLACK_BUY_CANDIDATE_CHANNEL", "")
SLACK_WATCHLIST_REPORT_WEBHOOK: Final[str] = os.getenv("SLACK_WATCHLIST_REPORT_WEBHOOK", "")
SLACK_WATCHLIST_REPORT_CHANNEL: Final[str] = os.getenv("SLACK_WATCHLIST_REPORT_CHANNEL", "")
# 레거시 (브리핑·미사용 US 등 — 신규 알림에는 사용하지 않음)
SLACK_CHANNEL_KR: Final[str] = os.getenv("SLACK_CHANNEL_KR", "")
SLACK_CHANNEL_US: Final[str] = os.getenv("SLACK_CHANNEL_US", "")
FIREBASE_STORAGE_BUCKET: Final[str] = os.getenv("FIREBASE_STORAGE_BUCKET", "")
FIREBASE_KEY_PATH: Final[str] = os.getenv(
    "FIREBASE_KEY_PATH",
    "cole-c3f96-firebase-adminsdk-fbsvc-be477d7ab7.json",
)

# Reserved for future integrations
KIS_APP_KEY: Final[str] = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET: Final[str] = os.getenv("KIS_APP_SECRET", "")
KIS_ACCOUNT_NO: Final[str] = os.getenv("KIS_ACCOUNT_NO", "")
EBEST_APP_KEY: Final[str] = os.getenv("EBEST_APP_KEY", "")
EBEST_APP_SECRET: Final[str] = os.getenv("EBEST_APP_SECRET", "")
KRX_ID: Final[str] = os.getenv("KRX_ID", "")
KRX_PW: Final[str] = os.getenv("KRX_PW", "")
DART_API_KEY: Final[str] = os.getenv("DART_API_KEY", "")
NAVER_CLIENT_ID: Final[str] = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET: Final[str] = os.getenv("NAVER_CLIENT_SECRET", "")

GROK_BASE_URL: Final[str] = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")

# AI model policy — single source: ai_models.py (02_AI_MODEL_POLICY.md)
from ai_models import (  # noqa: E402
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_DRAFT_MODEL,
    DEEPSEEK_VOTE_MODEL,
    GEMINI_FLASH_MODEL,
    GEMINI_PRO_MODEL,
    GEMINI_RISK_MODEL,
    GEMINI_SUMMARY_FALLBACK_MODEL,
    GEMINI_SUMMARY_MODEL,
    GROK_MODEL,
    GROK_VOTE_MODEL,
    KR_REPORT_STAGE_TIER,
    ModelTier,
    model_for_tier,
    policy_snapshot,
    tier_for_stage,
)

# ---- Data source switches ----
DATA_SOURCES: Final[dict[str, dict[str, str | bool]]] = {
    "yfinance": {"enabled": True, "required_env": "", "description": "US ETF/indices"},
    "pykrx": {"enabled": True, "required_env": "", "description": "KR market/flows"},
    "grok": {"enabled": bool(GROK_API_KEY), "required_env": "GROK_API_KEY", "description": "Realtime buzz"},
    "gemini": {"enabled": bool(GEMINI_API_KEY), "required_env": "GEMINI_API_KEY", "description": "AI synthesis"},
    "deepseek": {
        "enabled": bool(DEEPSEEK_API_KEY),
        "required_env": "DEEPSEEK_API_KEY",
        "description": "Draft/vote analysis",
    },
    "slack": {
        "enabled": bool(
            SLACK_BOT_TOKEN
            and (
                SLACK_BUY_CANDIDATE_WEBHOOK
                or SLACK_BUY_CANDIDATE_CHANNEL
                or SLACK_CHANNEL_KR
            )
            and (
                SLACK_WATCHLIST_REPORT_WEBHOOK
                or SLACK_WATCHLIST_REPORT_CHANNEL
            )
        ),
        "required_env": "SLACK_BOT_TOKEN+(BUY_CANDIDATE|WATCHLIST_REPORT destination)",
        "description": "Alert delivery (buy candidate + watchlist dawn report)",
    },
    "firebase": {
        "enabled": bool(FIREBASE_STORAGE_BUCKET),
        "required_env": "FIREBASE_STORAGE_BUCKET",
        "description": "Data retention",
    },
    "kis": {"enabled": bool(KIS_APP_KEY and KIS_APP_SECRET), "required_env": "KIS_APP_KEY/KIS_APP_SECRET", "description": "Realtime KR"},
    "ebest": {"enabled": bool(EBEST_APP_KEY and EBEST_APP_SECRET), "required_env": "EBEST_APP_KEY/EBEST_APP_SECRET", "description": "Future fundamentals"},
    "dart": {
        "enabled": bool(DART_API_KEY),
        "required_env": "DART_API_KEY",
        "description": "KR disclosure (Open DART)",
    },
    "naver_news": {
        "enabled": bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET),
        "required_env": "NAVER_CLIENT_ID+NAVER_CLIENT_SECRET",
        "description": "Naver search news",
    },
}

# ---- US sector ETF universe (SPDR 11 + AI specialized) ----
US_SECTOR_ETFS: Final[dict[str, str]] = {
    "기술": "XLK",
    "산업재": "XLI",
    "에너지": "XLE",
    "금융": "XLF",
    "헬스케어": "XLV",
    "소재": "XLB",
    "유틸리티": "XLU",
    "부동산": "XLRE",
    "필수소비": "XLP",
    "임의소비": "XLY",
    "통신": "XLC",
    "반도체": "SMH",
    "빅테크": "QQQ",
    "방산": "ITA",
    "클라우드": "SKYY",
    "AI인프라": "BOTZ",
}

# ---- KR watchlist (data/kr_watchlist.json — 5섹터·25종목 고정) ----
def _kr_watchlist_from_json() -> dict[str, dict[str, str]]:
    """config ↔ data 순환 import 방지: JSON 직접 로드."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "data" / "kr_watchlist.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    order = (
        "semiconductor_materials",
        "semiconductor_parts",
        "semiconductor_equipment",
        "defense_space",
        "shipbuilding_materials",
    )
    out: dict[str, dict[str, str]] = {}
    sectors = raw.get("sectors") or {}
    for key in order:
        block = sectors.get(key) or {}
        theme = str(block.get("label", key))
        for item in block.get("stocks") or []:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker", "")).strip().zfill(6)
            name = str(item.get("name", "")).strip()
            if ticker and name:
                out.setdefault(theme, {})[ticker] = name
    return out


KR_WATCHLIST: Final[dict[str, dict[str, str]]] = _kr_watchlist_from_json()

# ---- US watchlist (ticker -> name per theme) ----
US_WATCHLIST: Final[dict[str, dict[str, str]]] = {
    "빅테크 M7": {
        "NVDA": "NVIDIA",
        "AAPL": "Apple",
        "MSFT": "Microsoft",
        "GOOGL": "Google",
        "AMZN": "Amazon",
        "META": "Meta",
        "TSLA": "Tesla",
    },
    "반도체": {
        "AVGO": "Broadcom",
        "AMD": "AMD",
        "INTC": "Intel",
        "MU": "Micron",
        "SNDK": "Sandisk",
        "QCOM": "Qualcomm",
        "TXN": "Texas Instruments",
        "AMAT": "Applied Materials",
        "KLAC": "KLA",
        "LRCX": "Lam Research",
        "ARM": "ARM",
        "MRVL": "Marvell",
        "ADI": "Analog Devices",
        "MCHP": "Microchip",
        "ON": "ON Semiconductor",
        "MPWR": "Monolithic Power",
    },
    "소프트웨어": {
        "CRM": "Salesforce",
        "NOW": "ServiceNow",
        "SNOW": "Snowflake",
        "PLTR": "Palantir",
        "TEAM": "Atlassian",
        "ADBE": "Adobe",
        "ORCL": "Oracle",
        "SAP": "SAP",
        "INTU": "Intuit",
        "PANW": "Palo Alto",
    },
    "데이터센터": {
        "EQIX": "Equinix",
        "DLR": "Digital Realty",
        "IRM": "Iron Mountain",
        "SMCI": "Supermicro",
        "DELL": "Dell",
        "HPE": "HP Enterprise",
    },
    "AI 전력 인프라": {
        "VST": "Vistra",
        "CEG": "Constellation",
        "GEV": "GE Vernova",
        "ETN": "Eaton",
        "VRT": "Vertiv",
        "ENPH": "Enphase",
        "NEE": "NextEra",
        "AES": "AES Corp",
    },
    "하드웨어": {
        "ANET": "Arista Networks",
        "CSCO": "Cisco",
        "HPQ": "HP",
        "ZBRA": "Zebra Tech",
    },
}

# ---- Volume spike emoji thresholds (vs 20-day average) ----
VOLUME_FIRE: Final[float] = 30.0  # 30x+
VOLUME_BOLT: Final[float] = 15.0  # 15x+

# ---- Buy candidate price filters (KRW) ----
KR_MAX_PRICE: Final[int | None] = None
US_MAX_PRICE_KRW: Final[int] = 300_000

# ---- Sector temperature rules ----
HOT_RETURN_THRESHOLD: Final[float] = 2.0
HOT_VOLUME_RATIO_THRESHOLD: Final[float] = 1.3
WARM_RETURN_MIN: Final[float] = 0.5
FLAT_RETURN_MIN: Final[float] = -0.5
COLD_RETURN_MAX: Final[float] = -2.0

# ---- Dynamic discovery parameters ----
DISCOVERY_TOP_N: Final[int] = 20
DISCOVERY_FINAL_MIN: Final[int] = 30
DISCOVERY_FINAL_MAX: Final[int] = 40
VOLUME_RATIO_MUST_INCLUDE: Final[float] = 2.0
VOLUME_RATIO_INCLUDE: Final[float] = 1.5

# ---- Core fixed stocks ----
CORE_TICKERS: Final[dict[str, str]] = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "현대차": "005380",
    "기아": "000270",
    "LS일렉트릭": "010120",
}

# ---- Sector watchlist (reference set for analysis) ----
KR_SECTOR_STOCKS: Final[dict[str, dict[str, str]]] = {
    "AI반도체소부장": {
        "한미반도체": "042700",
        "리노공업": "058470",
        "HPSP": "403870",
        "주성엔지니어링": "036930",
        "원익IPS": "240810",
        "이오테크닉스": "039030",
        "피에스케이홀딩스": "460850",
        "ISC": "095340",
    },
    "AI반도체대형주": {
        "삼성전자": "005930",
        "SK하이닉스": "000660",
    },
    "AI전력데이터센터": {
        "LS일렉트릭": "010120",
        "효성중공업": "298040",
        "HD현대일렉트릭": "267260",
        "산일전기": "062040",
        "두산에너빌리티": "034020",
    },
    "방산": {
        "한화에어로스페이스": "012450",
        "LIG넥스원": "079550",
        "현대로템": "064350",
        "풍산": "103140",
    },
    "조선해양방산": {
        "HD한국조선해양": "009540",
        "한화오션": "042660",
        "삼성중공업": "010140",
        "HD현대미포": "010620",
    },
    "자동차": {
        "현대차": "005380",
        "기아": "000270",
        "현대모비스": "012330",
    },
}

RETENTION_DAYS: Final[int] = 14
