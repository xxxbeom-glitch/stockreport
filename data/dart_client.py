"""Open DART 공시 API (선택 — .env 의 DART_API_KEY)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from data.api_env import getenv

logger = logging.getLogger(__name__)

DART_API_BASE = "https://opendart.fss.or.kr/api"
_WARNED_NO_KEY = False
_STOCK_TO_CORP: dict[str, str] | None = None

DART_IMPORTANT_KEYWORDS: tuple[str, ...] = (
    "단일판매",
    "공급계약",
    "신규시설투자",
    "유상증자",
    "전환사채",
    "자기주식",
    "실적",
    "잠정실적",
    "최대주주",
    "소송",
)

DART_DEFAULT_DAYS = 30
DART_TOP_N = 3


def get_dart_api_key() -> str:
    return getenv("DART_API_KEY")


def is_dart_configured() -> bool:
    return bool(get_dart_api_key())


def _warn_skip_once() -> None:
    global _WARNED_NO_KEY
    if _WARNED_NO_KEY:
        return
    _WARNED_NO_KEY = True
    logger.warning(
        "DART_API_KEY 없음 — DART 공시 수집을 건너뜁니다 (.env에 DART_API_KEY 설정)"
    )


def _dart_get(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    import requests

    key = get_dart_api_key()
    if not key:
        _warn_skip_once()
        return None
    url = f"{DART_API_BASE}/{path}"
    try:
        resp = requests.get(url, params={**params, "crtfc_key": key}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return None
        status = str(data.get("status", ""))
        if status and status != "000":
            logger.warning(
                "DART API 오류 (status=%s, message=%s)",
                status,
                data.get("message", ""),
            )
            return None
        return data
    except Exception as exc:
        logger.warning("DART API 요청 실패: %s", type(exc).__name__)
        return None


def _load_stock_to_corp_code() -> dict[str, str]:
    """Open DART corpCode.xml — stock_code → corp_code (세션 캐시)."""
    global _STOCK_TO_CORP
    if _STOCK_TO_CORP is not None:
        return _STOCK_TO_CORP

    key = get_dart_api_key()
    if not key:
        _warn_skip_once()
        _STOCK_TO_CORP = {}
        return _STOCK_TO_CORP

    import io
    import zipfile
    import xml.etree.ElementTree as ET

    import requests

    try:
        resp = requests.get(
            f"{DART_API_BASE}/corpCode.xml",
            params={"crtfc_key": key},
            timeout=60,
        )
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_names:
                raise ValueError("corpCode zip에 XML 없음")
            root = ET.fromstring(zf.read(xml_names[0]))
    except Exception as exc:
        logger.warning("DART corpCode.xml 로드 실패: %s", type(exc).__name__)
        _STOCK_TO_CORP = {}
        return _STOCK_TO_CORP

    mapping: dict[str, str] = {}
    for item in root.findall("list"):
        stock = (item.findtext("stock_code") or "").strip().zfill(6)
        corp = (item.findtext("corp_code") or "").strip()
        if stock and corp:
            mapping[stock] = corp
    _STOCK_TO_CORP = mapping
    logger.info("DART corpCode 매핑 %d건 로드", len(mapping))
    return _STOCK_TO_CORP


def _resolve_corp_code(stock_code: str) -> str | None:
    code = str(stock_code).strip().zfill(6)
    return _load_stock_to_corp_code().get(code)


def is_important_disclosure(report_nm: str) -> bool:
    name = str(report_nm or "")
    return any(kw in name for kw in DART_IMPORTANT_KEYWORDS)


def fetch_disclosure_items(
    stock_code: str,
    *,
    days: int = 30,
    max_items: int = 100,
) -> list[dict[str, Any]]:
    """최근 공시 목록. 키 없으면 skip + warning, [] 반환."""
    if not is_dart_configured():
        _warn_skip_once()
        return []

    corp_code = _resolve_corp_code(stock_code)
    if not corp_code:
        return []

    end = datetime.now()
    start = end - timedelta(days=max(days, 1))
    data = _dart_get(
        "list.json",
        {
            "corp_code": corp_code,
            "bgn_de": start.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "page_count": max(max_items, 1),
            "sort": "date",
            "sort_mth": "desc",
        },
    )
    if not data:
        return []

    items = data.get("list")
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for row in items[:max_items]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "report_nm": str(row.get("report_nm", "")).strip(),
                "rcept_dt": str(row.get("rcept_dt", "")).strip(),
                "flr_nm": str(row.get("flr_nm", "")).strip(),
                "corp_name": str(row.get("corp_name", "")).strip(),
                "source": "opendart",
            }
        )
    return out


def fetch_important_disclosure_items(
    stock_code: str,
    *,
    days: int = DART_DEFAULT_DAYS,
    top_n: int = DART_TOP_N,
) -> list[dict[str, Any]]:
    """최근 N일 공시 중 중요 키워드 매칭 top N."""
    all_items = fetch_disclosure_items(stock_code, days=days, max_items=100)
    matched: list[dict[str, Any]] = []
    for row in all_items:
        report_nm = str(row.get("report_nm") or "")
        if not is_important_disclosure(report_nm):
            continue
        keywords = [kw for kw in DART_IMPORTANT_KEYWORDS if kw in report_nm]
        matched.append({**row, "matched_keywords": keywords})

    def _sort_key(item: dict[str, Any]) -> str:
        return str(item.get("rcept_dt") or "")

    matched.sort(key=_sort_key, reverse=True)
    return matched[:top_n]


def fetch_disclosure_summary(
    stock_code: str,
    *,
    days: int = 14,
    max_items: int = 3,
) -> str | None:
    """최근 공시 제목 요약 (기존 호환)."""
    items = fetch_disclosure_items(stock_code, days=days, max_items=max_items)
    titles = [i["report_nm"] for i in items if i.get("report_nm")]
    if not titles:
        return None
    if len(titles) == 1:
        return f"최근 공시: {titles[0]}"
    return "최근 공시: " + "; ".join(titles)


def collect_dart_disclosures(
    stock_codes: list[str],
    *,
    days: int = 14,
) -> dict[str, str | None]:
    """티커별 공시 요약. 미설정 시 전체 skip."""
    if not is_dart_configured():
        _warn_skip_once()
        return {str(c).zfill(6): None for c in stock_codes}

    out: dict[str, str | None] = {}
    for raw in stock_codes:
        code = str(raw).strip().zfill(6)
        items = fetch_disclosure_items(code, days=days, max_items=3)
        if not items:
            out[code] = None
            continue
        titles = [i["report_nm"] for i in items if i.get("report_nm")]
        out[code] = (
            f"최근 공시: {titles[0]}"
            if len(titles) == 1
            else "최근 공시: " + "; ".join(titles)
        )
    return out
