"""Korea Investment & Securities OpenAPI client.

Base URL: https://openapi.koreainvestment.com:9443
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

import config

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_PATH = Path("outputs/kis_access_token.json")
TOKEN_TTL = timedelta(hours=23)

# KIS index codes (U: index market)
INDEX_CODES = {
    "KOSPI": "0001",
    "KOSDAQ": "1001",
}

MARKET_CLS = {
    "KOSPI": "1",
    "KOSDAQ": "2",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _num(value: Any) -> float | None:
    try:
        text = str(value).replace(",", "").strip()
        if not text or text in {"-", "None", "null"}:
            return None
        return float(text)
    except Exception:
        return None


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _fmt_price(value: float) -> str:
    return f"{value:,.2f}"


def _index_snapshot(name: str, price: float | None, change_rate: float | None) -> dict[str, Any] | None:
    if price is None:
        return None
    pct = change_rate if change_rate is not None else 0.0
    return {
        "name": name,
        "value": _fmt_price(price),
        "change": _fmt_pct(pct),
        "is_up": pct >= 0,
        "change_rate": pct,
    }


def _credentials_ready() -> bool:
    return bool(config.KIS_APP_KEY and config.KIS_APP_SECRET)


def _app_key_secret() -> tuple[str, str]:
    app_key = config.KIS_APP_KEY
    app_secret = config.KIS_APP_SECRET
    if len(app_key) > len(app_secret) * 2:
        return app_secret, app_key
    return app_key, app_secret


class KISClient:
    """KIS OpenAPI wrapper with token cache and safe None fallbacks."""

    def __init__(self) -> None:
        self.base_url = BASE_URL
        self.token_cache_path = TOKEN_CACHE_PATH

    def _read_cached_token(self) -> str | None:
        if not self.token_cache_path.exists():
            return None
        try:
            data = json.loads(self.token_cache_path.read_text(encoding="utf-8"))
            token = str(data.get("access_token", ""))
            issued_at = datetime.fromisoformat(str(data.get("issued_at", "")).replace("Z", "+00:00"))
            if token and _now() - issued_at < TOKEN_TTL:
                return token
        except Exception as exc:
            logger.debug("KIS token cache read failed: %s", exc)
        return None

    def _write_cached_token(self, token: str) -> None:
        self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"access_token": token, "issued_at": _now().isoformat()}
        self.token_cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _get_token(self, force_refresh: bool = False) -> str | None:
        """Issue and cache access_token (valid ~1 day)."""
        if not _credentials_ready():
            return None
        if not force_refresh:
            cached = self._read_cached_token()
            if cached:
                return cached
        url = f"{self.base_url}/oauth2/tokenP"
        app_key, app_secret = _app_key_secret()
        body = {"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret}
        try:
            res = requests.post(url, json=body, timeout=15)
            res.raise_for_status()
            token = str(res.json().get("access_token", ""))
            if token:
                self._write_cached_token(token)
                return token
        except Exception as exc:
            logger.warning("KIS token issue failed: %s", exc)
        return None

    def _headers(self, tr_id: str) -> dict[str, str] | None:
        token = self._get_token()
        if not token:
            return None
        app_key, app_secret = _app_key_secret()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any] | None:
        headers = self._headers(tr_id)
        if not headers:
            return None
        try:
            res = requests.get(f"{self.base_url}{path}", headers=headers, params=params, timeout=15)
            if res.status_code in {401, 403}:
                self._get_token(force_refresh=True)
                headers = self._headers(tr_id)
                if not headers:
                    return None
                res = requests.get(f"{self.base_url}{path}", headers=headers, params=params, timeout=15)
            res.raise_for_status()
            data = res.json()
            if str(data.get("rt_cd", "0")) not in {"0", ""}:
                logger.debug("KIS rt_cd error %s: %s", tr_id, data.get("msg1"))
                return None
            return data
        except Exception as exc:
            logger.debug("KIS GET failed %s: %s", tr_id, exc)
            return None

    def _index_from_kis(self, name: str, index_code: str) -> dict[str, Any] | None:
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-index-price",
            "FHPUP02100000",
            {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": index_code,
            },
        )
        if not data:
            return None
        output = data.get("output") or {}
        if isinstance(output, list):
            output = output[0] if output else {}
        if not isinstance(output, dict):
            return None
        price = _num(output.get("bstp_nmix_prpr") or output.get("stck_prpr") or output.get("prpr"))
        change_rate = _num(output.get("prdy_ctrt") or output.get("bstp_nmix_prdy_ctrt"))
        return _index_snapshot(name, price, change_rate)

    def get_kospi_index(self) -> dict[str, Any] | None:
        return self._index_from_kis("KOSPI", INDEX_CODES["KOSPI"])

    def get_kosdaq_index(self) -> dict[str, Any] | None:
        return self._index_from_kis("KOSDAQ", INDEX_CODES["KOSDAQ"])

    def get_price(self, ticker: str) -> dict[str, Any] | None:
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker.zfill(6)},
        )
        if not data:
            return None
        output = data.get("output") or {}
        if not isinstance(output, dict) or not output:
            return None
        price = _num(output.get("stck_prpr"))
        if price is None:
            return None
        return {
            "ticker": ticker.zfill(6),
            "price": price,
            "change_rate": _num(output.get("prdy_ctrt")) or 0.0,
            "volume": _num(output.get("acml_vol")) or 0.0,
            "raw": output,
        }

    def get_52w_high_low(self, ticker: str) -> dict[str, float] | None:
        quote = self.get_price(ticker)
        if not quote:
            return None
        raw = quote.get("raw") or {}
        high = _num(raw.get("w52_hgpr"))
        low = _num(raw.get("w52_lwpr"))
        if high is None and low is None:
            return None
        return {"high_52": high or 0.0, "low_52": low or 0.0}

    def get_foreign_net(self, ticker: str) -> float | None:
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-investor",
            "FHKST01010900",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker.zfill(6)},
        )
        if not data:
            return None
        output = data.get("output") or {}
        if isinstance(output, list):
            output = output[0] if output else {}
        if not isinstance(output, dict):
            return None
        value = _num(
            output.get("frgn_ntby_tr_pbmn")
            or output.get("frgn_ntby_qty")
            or output.get("frgn_seln_vol")
        )
        return value

    def get_top_volume(self, market: str = "KOSPI", n: int = 5) -> list[dict[str, Any]] | None:
        cls = MARKET_CLS.get(market.upper(), "1")
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": "0000",
                "FID_DIV_CLS_CODE": "0",
                "FID_BLNG_CLS_CODE": "0",
                "FID_TRGT_CLS_CODE": cls,
                "FID_TRGT_EXLS_CLS_CODE": "0",
                "FID_INPUT_PRICE_1": "0",
                "FID_INPUT_PRICE_2": "0",
                "FID_VOL_CNT": str(max(n, 5)),
                "FID_INPUT_DATE_1": "",
            },
        )
        if not data:
            return None
        rows = data.get("output") or []
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or not rows:
            return None
        leaders: list[dict[str, Any]] = []
        for row in rows[:n]:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("mksc_shrn_iscd") or row.get("stck_shrn_iscd") or "").strip()
            if not ticker:
                continue
            name = str(row.get("hts_kor_isnm") or row.get("prdt_name") or ticker)
            price = _num(row.get("stck_prpr"))
            change_rate = _num(row.get("prdy_ctrt")) or 0.0
            vol_ratio = _num(row.get("vol_inrt") or row.get("vol_tnrt")) or 0.0
            leaders.append(
                {
                    "ticker": ticker.zfill(6),
                    "name": name,
                    "market": market.upper(),
                    "price": price,
                    "change_rate": change_rate,
                    "volume_ratio": vol_ratio,
                    "is_up": change_rate >= 0,
                }
            )
        return leaders or None


_default_client: KISClient | None = None


def _client() -> KISClient:
    global _default_client
    if _default_client is None:
        _default_client = KISClient()
    return _default_client


def _get_token(force_refresh: bool = False) -> str | None:
    return _client()._get_token(force_refresh=force_refresh)


def get_kospi_index() -> dict[str, Any] | None:
    return _client().get_kospi_index()


def get_kosdaq_index() -> dict[str, Any] | None:
    return _client().get_kosdaq_index()


def get_price(ticker: str) -> dict[str, Any] | None:
    return _client().get_price(ticker)


def get_52w_high_low(ticker: str) -> dict[str, float] | None:
    return _client().get_52w_high_low(ticker)


def get_foreign_net(ticker: str) -> float | None:
    return _client().get_foreign_net(ticker)


def get_top_volume(market: str = "KOSPI", n: int = 5) -> list[dict[str, Any]] | None:
    return _client().get_top_volume(market=market, n=n)


# Backward compatibility
get_access_token = _get_token
get_investor_flow = lambda t: {"foreign_net": get_foreign_net(t)}


if __name__ == "__main__":
    from dotenv import load_dotenv as _load

    _load()
    c = KISClient()
    print("token", bool(_get_token()))
    print("kospi", c.get_kospi_index())
    print("kosdaq", c.get_kosdaq_index())
    print("price", c.get_price("005930"))
    print("top", c.get_top_volume("KOSPI", 3))
