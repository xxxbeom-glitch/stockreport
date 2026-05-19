"""Korea Investment & Securities OpenAPI client.

Uses the real investment domain:
https://openapi.koreainvestment.com:9443
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

import config

load_dotenv()

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_PATH = Path("outputs/kis_access_token.json")
TOKEN_TTL = timedelta(hours=23)


def _now() -> datetime:
    return datetime.now(UTC)


def _credentials_ready() -> bool:
    return bool(config.KIS_APP_KEY and config.KIS_APP_SECRET)


def _app_key_secret() -> tuple[str, str]:
    """Return app key/secret, correcting common swapped env assignment."""
    app_key = config.KIS_APP_KEY
    app_secret = config.KIS_APP_SECRET
    # KIS app secret is typically much longer than app key. If swapped,
    # correct it locally without mutating environment variables.
    if len(app_key) > len(app_secret) * 2:
        return app_secret, app_key
    return app_key, app_secret


def _read_cached_token() -> str:
    if not TOKEN_CACHE_PATH.exists():
        return ""
    try:
        data = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
        token = str(data.get("access_token", ""))
        issued_at = datetime.fromisoformat(str(data.get("issued_at", "")).replace("Z", "+00:00"))
        if token and _now() - issued_at < TOKEN_TTL:
            return token
    except Exception:
        return ""
    return ""


def _write_cached_token(token: str) -> None:
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"access_token": token, "issued_at": _now().isoformat()}
    TOKEN_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_access_token(force_refresh: bool = False) -> str:
    """Issue and cache KIS access_token."""
    if not _credentials_ready():
        return ""
    if not force_refresh:
        cached = _read_cached_token()
        if cached:
            return cached

    url = f"{BASE_URL}/oauth2/tokenP"
    app_key, app_secret = _app_key_secret()
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret,
    }
    try:
        res = requests.post(url, json=body, timeout=15)
        res.raise_for_status()
        data = res.json()
        token = str(data.get("access_token", ""))
        if token:
            _write_cached_token(token)
        return token
    except Exception:
        return ""


def _headers(tr_id: str) -> dict[str, str]:
    token = get_access_token()
    if not token:
        return {}
    app_key, app_secret = _app_key_secret()
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P",
    }


def _get(path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
    headers = _headers(tr_id)
    if not headers:
        return {}
    try:
        res = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=15)
        # One retry on expired token.
        if res.status_code in {401, 403}:
            get_access_token(force_refresh=True)
            headers = _headers(tr_id)
            res = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        if str(data.get("rt_cd", "0")) not in {"0", ""}:
            return {}
        return data
    except Exception:
        return {}


def _num(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def get_price(ticker: str) -> dict[str, Any]:
    """Return current price, change rate, and volume for a KR stock ticker."""
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        },
    )
    output = data.get("output") or {}
    if not isinstance(output, dict) or not output:
        return {}
    return {
        "ticker": ticker,
        "price": _num(output.get("stck_prpr")),
        "change_rate": _num(output.get("prdy_ctrt")),
        "volume": _num(output.get("acml_vol")),
        "raw": output,
    }


def get_investor_flow(ticker: str) -> dict[str, Any]:
    """Return institution/foreign/individual net-buy flow when available."""
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-investor",
        "FHKST01010900",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        },
    )
    output = data.get("output") or {}
    if isinstance(output, list):
        output = output[0] if output else {}
    if not isinstance(output, dict) or not output:
        return {}

    return {
        "ticker": ticker,
        "foreign_net": _num(
            output.get("frgn_ntby_tr_pbmn")
            or output.get("frgn_ntby_qty")
            or output.get("frgn_seln_vol")
        ),
        "institution_net": _num(
            output.get("orgn_ntby_tr_pbmn")
            or output.get("orgn_ntby_qty")
            or output.get("istt_seln_vol")
        ),
        "individual_net": _num(
            output.get("prsn_ntby_tr_pbmn")
            or output.get("prsn_ntby_qty")
            or output.get("prsn_seln_vol")
        ),
        "raw": output,
    }


def get_foreign_net(ticker: str) -> float:
    """Return foreign net-buy amount for a KR stock ticker."""
    return float(get_investor_flow(ticker).get("foreign_net", 0.0) or 0.0)
