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
    if len(app_key) > len(app_secret) * 2:
        return app_secret, app_key
    return app_key, app_secret


def _num(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


class KISClient:
    """Korea Investment & Securities OpenAPI client wrapper."""

    def __init__(self) -> None:
        self.base_url = BASE_URL
        self.token_cache_path = TOKEN_CACHE_PATH

    def _read_cached_token(self) -> str:
        if not self.token_cache_path.exists():
            return ""
        try:
            data = json.loads(self.token_cache_path.read_text(encoding="utf-8"))
            token = str(data.get("access_token", ""))
            issued_at = datetime.fromisoformat(str(data.get("issued_at", "")).replace("Z", "+00:00"))
            if token and _now() - issued_at < TOKEN_TTL:
                return token
        except Exception:
            return ""
        return ""

    def _write_cached_token(self, token: str) -> None:
        self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"access_token": token, "issued_at": _now().isoformat()}
        self.token_cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Issue and cache KIS access_token."""
        if not _credentials_ready():
            return ""
        if not force_refresh:
            cached = self._read_cached_token()
            if cached:
                return cached

        url = f"{self.base_url}/oauth2/tokenP"
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
                self._write_cached_token(token)
            return token
        except Exception:
            return ""

    def _headers(self, tr_id: str) -> dict[str, str]:
        token = self.get_access_token()
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

    def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
        headers = self._headers(tr_id)
        if not headers:
            return {}
        try:
            res = requests.get(f"{self.base_url}{path}", headers=headers, params=params, timeout=15)
            if res.status_code in {401, 403}:
                self.get_access_token(force_refresh=True)
                headers = self._headers(tr_id)
                res = requests.get(f"{self.base_url}{path}", headers=headers, params=params, timeout=15)
            res.raise_for_status()
            data = res.json()
            if str(data.get("rt_cd", "0")) not in {"0", ""}:
                return {}
            return data
        except Exception:
            return {}

    def get_price(self, ticker: str) -> dict[str, Any]:
        """Return current price, change rate, and volume for a KR stock ticker."""
        data = self._get(
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

    def get_investor_flow(self, ticker: str) -> dict[str, Any]:
        """Return institution/foreign/individual net-buy flow when available."""
        data = self._get(
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

    def get_foreign_net(self, ticker: str) -> float:
        """Return foreign net-buy amount for a KR stock ticker."""
        return float(self.get_investor_flow(ticker).get("foreign_net", 0.0) or 0.0)

    def get_kospi_index(self) -> dict[str, Any]:
        """Return KOSPI index snapshot (value, change, is_up)."""
        from .kr_market import get_kr_indices

        return get_kr_indices().get(
            "KOSPI",
            {"name": "KOSPI", "value": "N/A", "change": "N/A", "is_up": None},
        )

    def get_kosdaq_index(self) -> dict[str, Any]:
        """Return KOSDAQ index snapshot (value, change, is_up)."""
        from .kr_market import get_kr_indices

        return get_kr_indices().get(
            "KOSDAQ",
            {"name": "KOSDAQ", "value": "N/A", "change": "N/A", "is_up": None},
        )


# Backward-compatible module-level wrappers
_default_client: KISClient | None = None


def _client() -> KISClient:
    global _default_client
    if _default_client is None:
        _default_client = KISClient()
    return _default_client


def get_access_token(force_refresh: bool = False) -> str:
    return _client().get_access_token(force_refresh=force_refresh)


def get_price(ticker: str) -> dict[str, Any]:
    return _client().get_price(ticker)


def get_investor_flow(ticker: str) -> dict[str, Any]:
    return _client().get_investor_flow(ticker)


def get_foreign_net(ticker: str) -> float:
    return _client().get_foreign_net(ticker)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    client = KISClient()
    print(client.get_kospi_index())
    print(client.get_kosdaq_index())