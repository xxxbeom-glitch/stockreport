"""Korea Investment & Securities OpenAPI client.

Base URL: https://openapi.koreainvestment.com:9443
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests import HTTPError

import config
from data.kis_rate_limit import (
    configured_backoff_sec,
    configured_max_retries,
    is_kis_rate_limit_halted,
    is_rate_limit_msg,
    kis_http_request,
    kis_rate_limit_observability,
    parse_rate_limit_from_response,
    record_kis_rate_limit_error,
    reset_kis_rate_limit_state,
)

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443").rstrip("/")
KIS_VTS_BASE_URL = "https://openapivts.koreainvestment.com:29443"
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

# 업종 구분별 전체시세 (누적 거래대금·등락률)
SECTOR_CATEGORY_TR_ID = "FHPUP02140000"
SECTOR_CATEGORY_PATH = "/uapi/domestic-stock/v1/quotations/inquire-index-category-price"
SECTOR_CATEGORY_PARAMS = {
    "KOSPI": ("0001", "K", "3"),
    "KOSDAQ": ("1001", "Q", "3"),
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


def _ccnl_tick_buy_sell(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Classify inquire-ccnl ticks into buy/sell volume by price direction."""
    ordered = sorted(rows, key=lambda r: str(r.get("stck_cntg_hour", "")))
    buy = 0
    sell = 0
    prev_price: float | None = None
    for row in ordered:
        vol = _num(row.get("cntg_vol"))
        price = _num(row.get("stck_prpr"))
        if vol is None or vol <= 0 or price is None:
            continue
        vol_i = int(vol)
        sign = str(row.get("prdy_vrss_sign", "3"))
        if prev_price is None:
            if sign in ("1", "2"):
                buy += vol_i
            elif sign in ("4", "5"):
                sell += vol_i
            else:
                buy += vol_i // 2
                sell += vol_i - vol_i // 2
        elif price > prev_price:
            buy += vol_i
        elif price < prev_price:
            sell += vol_i
        elif sign in ("1", "2"):
            buy += vol_i
        elif sign in ("4", "5"):
            sell += vol_i
        else:
            buy += vol_i // 2
            sell += vol_i - vol_i // 2
        prev_price = price
    return buy, sell


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


def credentials_diagnostics() -> dict[str, Any]:
    """Safe env check — never logs secret values."""
    endpoint_mode = "vts" if "openapivts" in BASE_URL else "production"
    return {
        "configured": _credentials_ready(),
        "app_key_len": len((config.KIS_APP_KEY or "").strip()),
        "app_secret_len": len((config.KIS_APP_SECRET or "").strip()),
        "base_url": BASE_URL,
        "endpoint_mode": endpoint_mode,
        "expected_production_url": "https://openapi.koreainvestment.com:9443",
        "expected_vts_url": KIS_VTS_BASE_URL,
        "token_path": str(TOKEN_CACHE_PATH),
    }


def _kis_app_credentials() -> tuple[str, str]:
    """Use KIS_APP_KEY / KIS_APP_SECRET as documented (no silent swap)."""
    return (config.KIS_APP_KEY or "").strip(), (config.KIS_APP_SECRET or "").strip()


def _safe_kis_error_from_response(res: requests.Response) -> dict[str, Any]:
    meta: dict[str, Any] = {"http_status": res.status_code}
    text = (res.text or "").strip()
    if not text:
        return meta
    try:
        body = res.json()
        if isinstance(body, dict):
            for key in ("msg_cd", "msg1", "error_code", "error_description", "rt_cd"):
                val = body.get(key)
                if val not in (None, ""):
                    meta[key] = str(val)[:500]
    except json.JSONDecodeError:
        meta["body_prefix"] = text[:200]
    return meta


class KISClient:
    """KIS OpenAPI wrapper with token cache and safe None fallbacks."""

    _token_lock = threading.Lock()

    def __init__(self) -> None:
        self.base_url = BASE_URL
        self.token_cache_path = TOKEN_CACHE_PATH
        self._memory_token: str | None = None
        self._memory_issued_at: datetime | None = None
        self._token_issue_calls: int = 0
        self._token_refresh_attempts: int = 0
        self._auth_failed: bool = False
        self.last_auth_error: dict[str, Any] = {}

    def reset_auth_state(self, *, clear_token: bool = False) -> None:
        """Test/helper reset — clears fail-fast latch and optional in-memory token."""
        with self._token_lock:
            self._auth_failed = False
            self._token_refresh_attempts = 0
            if clear_token:
                self._memory_token = None
                self._memory_issued_at = None

    def _token_still_valid(self) -> bool:
        return bool(
            self._memory_token
            and self._memory_issued_at
            and _now() - self._memory_issued_at < TOKEN_TTL
        )

    def _read_cached_token(self) -> str | None:
        if not self.token_cache_path.exists():
            return None
        try:
            data = json.loads(self.token_cache_path.read_text(encoding="utf-8"))
            token = str(data.get("access_token", ""))
            issued_at = datetime.fromisoformat(str(data.get("issued_at", "")).replace("Z", "+00:00"))
            if token and _now() - issued_at < TOKEN_TTL:
                self._memory_token = token
                self._memory_issued_at = issued_at
                return token
        except Exception as exc:
            logger.debug("KIS token cache read failed: %s", exc)
        return None

    def _write_cached_token(self, token: str) -> None:
        self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        issued = _now()
        self._memory_issued_at = issued
        payload = {"access_token": token, "issued_at": issued.isoformat()}
        self.token_cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _issue_token_http(self) -> dict[str, Any]:
        """Single POST /oauth2/tokenP — caller must hold _token_lock."""
        self._token_issue_calls += 1
        app_key, app_secret = _kis_app_credentials()
        url = f"{self.base_url}/oauth2/tokenP"
        body = {"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret}
        try:
            res = kis_http_request("POST", url, tr_id="tokenP", json=body, timeout=15)
            if res is None:
                return {"ok": False, "error": "kis_rate_limit_exceeded"}
            if res.status_code >= 400:
                meta = _safe_kis_error_from_response(res)
                meta.update({"ok": False, "error": "kis_auth_failed", "endpoint": "/oauth2/tokenP"})
                logger.warning("KIS token issue failed: %s", meta)
                return meta
            text = (res.text or "").strip()
            if not text:
                meta = {"ok": False, "error": "kis_auth_failed", "http_status": res.status_code, "detail": "empty_body"}
                logger.warning("KIS token issue empty response status=%s", res.status_code)
                return meta
            try:
                payload = res.json()
            except json.JSONDecodeError:
                meta = {
                    "ok": False,
                    "error": "kis_auth_failed",
                    "http_status": res.status_code,
                    "body_prefix": text[:200],
                }
                logger.warning("KIS token issue non-json: %s", meta)
                return meta
            token = str(payload.get("access_token", ""))
            if not token:
                meta = {"ok": False, "error": "kis_auth_failed", "http_status": res.status_code, "detail": "no_access_token"}
                meta.update({k: payload.get(k) for k in ("msg_cd", "msg1") if payload.get(k)})
                logger.warning("KIS token issue missing access_token: %s", meta)
                return meta
            self._memory_token = token
            self._write_cached_token(token)
            return {"ok": True, "http_status": res.status_code}
        except HTTPError as exc:
            res = exc.response
            meta = _safe_kis_error_from_response(res) if res is not None else {"http_status": None}
            meta.update({"ok": False, "error": "kis_auth_failed", "detail": type(exc).__name__})
            logger.warning("KIS token issue HTTP error: %s", meta)
            return meta
        except Exception as exc:
            meta = {"ok": False, "error": "kis_auth_failed", "detail": type(exc).__name__}
            logger.warning("KIS token issue failed: %s", meta)
            return meta

    def ensure_token(self, *, force_refresh: bool = False) -> str | None:
        """Thread-safe token: memory → disk → one tokenP issue."""
        if not _credentials_ready():
            self.last_auth_error = {"ok": False, "error": "kis_credentials_missing"}
            self._auth_failed = True
            return None
        with self._token_lock:
            if force_refresh:
                self._auth_failed = False
                self._memory_token = None
                self._memory_issued_at = None
            elif self._auth_failed:
                return None
            if not force_refresh and self._token_still_valid():
                return self._memory_token
            if not force_refresh and not self._memory_token:
                cached = self._read_cached_token()
                if cached:
                    return cached
            result = self._issue_token_http()
            self.last_auth_error = result
            if result.get("ok"):
                self._auth_failed = False
                return self._memory_token
            self._auth_failed = True
            return None

    def is_auth_failed(self) -> bool:
        return self._auth_failed

    def _auth_headers(self, tr_id: str) -> dict[str, str] | None:
        if not self._memory_token:
            return None
        app_key, app_secret = _kis_app_credentials()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._memory_token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def probe_authenticated_api(self) -> dict[str, Any]:
        """One lightweight GET to verify bearer token without re-issuing tokenP."""
        if self._auth_failed:
            return {"ok": False, "error": "kis_auth_failed", **dict(self.last_auth_error or {})}
        if not self._memory_token:
            return {"ok": False, "error": "no_token"}
        headers = self._auth_headers("FHKST01010100")
        if not headers:
            return {"ok": False, "error": "no_token"}
        try:
            res = kis_http_request(
                "GET",
                f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
                tr_id="FHKST01010100",
                headers=headers,
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"},
                timeout=15,
            )
            if res is None:
                return {"ok": False, "error": "kis_rate_limit_exceeded"}
            if res.status_code >= 400:
                meta = _safe_kis_error_from_response(res)
                meta.update({"ok": False, "error": "kis_probe_failed", "endpoint": "inquire-price"})
                return meta
            text = (res.text or "").strip()
            if not text:
                return {"ok": False, "error": "kis_probe_failed", "http_status": res.status_code, "detail": "empty_body"}
            try:
                payload = res.json()
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "error": "kis_probe_failed",
                    "http_status": res.status_code,
                    "body_prefix": text[:200],
                }
            if str(payload.get("rt_cd", "0")) not in {"0", ""}:
                return {
                    "ok": False,
                    "error": "kis_probe_failed",
                    "http_status": res.status_code,
                    "msg_cd": payload.get("msg_cd"),
                    "msg1": payload.get("msg1"),
                }
            return {"ok": True, "http_status": res.status_code, "probe": "inquire-price"}
        except Exception as exc:
            return {"ok": False, "error": "kis_probe_failed", "detail": type(exc).__name__}

    def _get_token(self, force_refresh: bool = False) -> str | None:
        return self.ensure_token(force_refresh=force_refresh)

    def _headers(self, tr_id: str) -> dict[str, str] | None:
        token = self.ensure_token()
        if not token:
            return None
        app_key, app_secret = _kis_app_credentials()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any] | None:
        if self._auth_failed or is_kis_rate_limit_halted():
            return None
        headers = self._headers(tr_id)
        if not headers:
            return None

        max_retries = configured_max_retries()
        backoff = configured_backoff_sec()
        url = f"{self.base_url}{path}"

        for attempt in range(max_retries + 1):
            if is_kis_rate_limit_halted():
                return None
            try:
                res = kis_http_request("GET", url, tr_id=tr_id, headers=headers, params=params, timeout=15)
                if res is None:
                    return None

                is_rl, rl_msg = parse_rate_limit_from_response(res)
                if is_rl:
                    record_kis_rate_limit_error(
                        tr_id=tr_id,
                        msg1=rl_msg,
                        retried=attempt > 0,
                    )
                    if is_kis_rate_limit_halted():
                        return None
                    if attempt < max_retries:
                        time.sleep(backoff * (attempt + 1))
                        continue
                    return None

                if res.status_code in {401, 403}:
                    meta = _safe_kis_error_from_response(res)
                    if not is_rate_limit_msg(meta.get("msg_cd")):
                        logger.warning("KIS GET auth error tr_id=%s %s", tr_id, meta)
                    if self._memory_token and self._token_refresh_attempts < 1 and not self._auth_failed:
                        self._token_refresh_attempts += 1
                        if self.ensure_token(force_refresh=True):
                            headers = self._headers(tr_id)
                            if not headers:
                                return None
                            res = kis_http_request(
                                "GET", url, tr_id=tr_id, headers=headers, params=params, timeout=15
                            )
                            if res is None:
                                return None
                            is_rl, rl_msg = parse_rate_limit_from_response(res)
                            if is_rl:
                                record_kis_rate_limit_error(tr_id=tr_id, msg1=rl_msg, retried=True)
                                return None
                            if res.status_code >= 400:
                                return None
                        else:
                            return None
                    else:
                        return None

                if res.status_code >= 400:
                    return None

                text = (res.text or "").strip()
                if not text:
                    logger.debug("KIS GET empty body tr_id=%s status=%s", tr_id, res.status_code)
                    return None
                try:
                    data = res.json()
                except json.JSONDecodeError:
                    if not is_kis_rate_limit_halted():
                        logger.warning(
                            "KIS GET non-json tr_id=%s status=%s body_prefix=%r",
                            tr_id,
                            res.status_code,
                            text[:120],
                        )
                    return None
                if not isinstance(data, dict):
                    return None

                msg_cd = data.get("msg_cd")
                if is_rate_limit_msg(msg_cd):
                    record_kis_rate_limit_error(
                        tr_id=tr_id,
                        msg1=str(data.get("msg1") or ""),
                        retried=attempt > 0,
                    )
                    if is_kis_rate_limit_halted():
                        return None
                    if attempt < max_retries:
                        time.sleep(backoff * (attempt + 1))
                        continue
                    return None

                if str(data.get("rt_cd", "0")) not in {"0", ""}:
                    if not is_rate_limit_msg(data.get("msg_cd")) and not is_kis_rate_limit_halted():
                        logger.warning(
                            "KIS rt_cd error tr_id=%s msg_cd=%s msg1=%s",
                            tr_id,
                            data.get("msg_cd"),
                            data.get("msg1"),
                        )
                    return None
                return data
            except Exception as exc:
                if not is_kis_rate_limit_halted():
                    logger.debug("KIS GET failed %s: %s", tr_id, exc)
                return None
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

    def get_sector_trading_value(self, market: str = "KOSPI") -> list[dict[str, Any]] | None:
        """업종별 거래대금·등락률 (KIS 국내업종 구분별전체시세).

        TR_ID FHPUP02140000 — 업종별 누적 거래대금(acml_tr_pbmn, 백만원) 일괄 조회.
        (FHKUP03500100 은 단일 업종 기간별 시세용이라 본 기능과 맞지 않음)
        """
        key = market.upper()
        sector_params = SECTOR_CATEGORY_PARAMS.get(key)
        if not sector_params:
            return None
        fid_input_iscd, fid_mrkt_cls_code, fid_blng_cls_code = sector_params
        data = self._get(
            SECTOR_CATEGORY_PATH,
            SECTOR_CATEGORY_TR_ID,
            {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": fid_input_iscd,
                "FID_COND_SCR_DIV_CODE": "20214",
                "FID_MRKT_CLS_CODE": fid_mrkt_cls_code,
                "FID_BLNG_CLS_CODE": fid_blng_cls_code,
            },
        )
        if not data:
            return None
        rows = data.get("output2") or []
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or not rows:
            return None
        result: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("hts_kor_isnm") or "").strip()
            if not name:
                continue
            pbmn_million = _num(row.get("acml_tr_pbmn"))
            if pbmn_million is None:
                continue
            trading_value_eok = round(pbmn_million / 100.0, 2)
            change_rate = _num(row.get("bstp_nmix_prdy_ctrt"))
            if change_rate is None:
                change_rate = 0.0
            result.append(
                {
                    "name": name,
                    "trading_value_eok": trading_value_eok,
                    "change_rate": change_rate,
                    "change": _fmt_pct(change_rate),
                }
            )
        if not result:
            return None
        result.sort(key=lambda x: x["trading_value_eok"], reverse=True)
        return result

    def get_conclusion_strength(self, ticker: str) -> dict[str, Any] | None:
        """종목 체결강도 (주식현재가 체결, FHKST01010300).

        최근 체결 건별 cntg_vol을 매수/매도로 분류한 뒤
        strength = buy_vol / sell_vol * 100 을 계산합니다.
        단일 가격만 이어질 때는 응답의 당일 체결강도(tday_rltv)로 비율을 보정합니다.
        """
        code = ticker.zfill(6)
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-ccnl",
            "FHKST01010300",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
        )
        if not data:
            return None
        rows = data.get("output") or []
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or not rows:
            return None

        buy_vol, sell_vol = _ccnl_tick_buy_sell(rows)
        total = buy_vol + sell_vol
        if total <= 0:
            return None

        if buy_vol == 0 or sell_vol == 0:
            day_strength = _num(rows[0].get("tday_rltv"))
            if day_strength is None or day_strength <= 0:
                return None
            sell_vol = int(round(total * 100 / (100 + day_strength)))
            buy_vol = total - sell_vol
            if sell_vol <= 0 or buy_vol <= 0:
                return None

        strength = round(buy_vol / sell_vol * 100, 1)
        return {"strength": strength, "buy_vol": buy_vol, "sell_vol": sell_vol}

    def get_daily_ohlcv_range(
        self,
        ticker: str,
        start_yyyymmdd: str,
        end_yyyymmdd: str,
    ) -> list[dict[str, Any]]:
        """Daily OHLCV bars for ticker between start and end (inclusive), oldest first."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            "FHKST03010100",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker.zfill(6),
                "FID_INPUT_DATE_1": start_yyyymmdd,
                "FID_INPUT_DATE_2": end_yyyymmdd,
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        if not data:
            return []
        rows = data.get("output2") or []
        if isinstance(rows, dict):
            rows = [rows]
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            date = str(row.get("stck_bsop_date") or "").strip()
            if len(date) != 8:
                continue
            close = _num(row.get("stck_clpr"))
            if close is None or close <= 0:
                continue
            op = int(_num(row.get("stck_oprc")) or 0)
            hi = int(_num(row.get("stck_hgpr")) or 0)
            lo = int(_num(row.get("stck_lwpr")) or 0)
            cl = int(close)
            vol = int(_num(row.get("acml_vol")) or 0)
            tv = int(_num(row.get("acml_tr_pbmn")) or 0)
            out.append(
                {
                    "date": date,
                    "open": op,
                    "high": hi,
                    "low": lo,
                    "close": cl,
                    "volume": vol,
                    "trading_value": tv,
                }
            )
        return sorted(out, key=lambda r: r["date"])


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


def get_daily_ohlcv_range(ticker: str, start_yyyymmdd: str, end_yyyymmdd: str) -> list[dict[str, Any]]:
    return _client().get_daily_ohlcv_range(ticker, start_yyyymmdd, end_yyyymmdd)


def credentials_ready() -> bool:
    return _credentials_ready()


def is_kis_auth_failed() -> bool:
    return _client().is_auth_failed()


def reset_kis_auth_state(*, clear_token: bool = False) -> None:
    _client().reset_auth_state(clear_token=clear_token)


def reset_kis_rate_limit() -> None:
    reset_kis_rate_limit_state()


def kis_rate_limit_summary() -> dict[str, Any]:
    return kis_rate_limit_observability()


def preflight_kis_auth(*, force_refresh: bool = False) -> dict[str, Any]:
    """
    Issue or reuse KIS token once before bulk REPLAY calls.
    On failure returns kis_auth_failed with safe KIS msg_cd/msg1 (no secrets).
    """
    diag = credentials_diagnostics()
    if not diag["configured"]:
        return {**diag, "ok": False, "error": "kis_credentials_missing"}

    client = _client()
    if force_refresh:
        client.reset_auth_state(clear_token=True)
    token = client.ensure_token(force_refresh=force_refresh)
    out: dict[str, Any] = {
        **diag,
        "ok": bool(token),
        "token_issue_calls": client._token_issue_calls,
    }
    if not token:
        err = dict(client.last_auth_error or {})
        err.setdefault("error", "kis_auth_failed")
        out.update(err)
        return out

    probe = client.probe_authenticated_api()
    if probe.get("ok"):
        out["token_source"] = "memory_or_disk_cache"
        out["probe"] = probe.get("probe")
        return out

    if not force_refresh:
        refreshed = client.ensure_token(force_refresh=True)
        out["token_issue_calls"] = client._token_issue_calls
        if refreshed:
            probe = client.probe_authenticated_api()
            if probe.get("ok"):
                out["ok"] = True
                out["token_source"] = "refreshed_after_probe"
                out["probe"] = probe.get("probe")
                return out

    client._auth_failed = True
    err = dict(client.last_auth_error or {})
    err.setdefault("error", "kis_auth_failed")
    probe_err = {k: probe.get(k) for k in ("http_status", "msg_cd", "msg1", "error") if probe.get(k)}
    out.update(err)
    out.update(probe_err)
    out["ok"] = False
    out["probe_failed"] = True
    return out


def get_top_volume(market: str = "KOSPI", n: int = 5) -> list[dict[str, Any]] | None:
    return _client().get_top_volume(market=market, n=n)


def get_sector_trading_value(market: str = "KOSPI") -> list[dict[str, Any]] | None:
    return _client().get_sector_trading_value(market=market)


def get_conclusion_strength(ticker: str) -> dict[str, Any] | None:
    return _client().get_conclusion_strength(ticker)


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
    print("sector_tv", c.get_sector_trading_value())
    print("strength", c.get_conclusion_strength("005930"))
