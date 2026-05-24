"""Process-wide KIS REST rate limiting, metering, and EGW00201 circuit breaker."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any

import requests

logger = logging.getLogger(__name__)

KIS_RATE_LIMIT_MSG_CD = "EGW00201"

_DEFAULT_RPS = 1.0
_DEFAULT_MAX_RETRIES = 1
_DEFAULT_BACKOFF_SEC = 1.0
_DEFAULT_HALT_AFTER = 1
_DEFAULT_MAX_REQUESTS_PER_RUN = 80
_DEFAULT_ENRICH_WORKERS = 1


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def configured_max_rps() -> float:
    return max(0.1, _env_float("KIS_MAX_REQUESTS_PER_SECOND", _DEFAULT_RPS))


def configured_max_retries() -> int:
    return max(0, _env_int("KIS_RATE_LIMIT_MAX_RETRIES", _DEFAULT_MAX_RETRIES))


def configured_backoff_sec() -> float:
    return max(0.05, _env_float("KIS_RATE_LIMIT_BACKOFF_SEC", _DEFAULT_BACKOFF_SEC))


def configured_halt_after() -> int:
    return max(1, _env_int("KIS_RATE_LIMIT_HALT_AFTER", _DEFAULT_HALT_AFTER))


def configured_enrich_max_workers() -> int:
    return max(1, _env_int("KIS_ENRICH_MAX_WORKERS", _DEFAULT_ENRICH_WORKERS))


def configured_max_requests_per_run() -> int:
    return max(1, _env_int("KIS_MAX_REQUESTS_PER_RUN", _DEFAULT_MAX_REQUESTS_PER_RUN))


def kis_requests_used() -> int:
    return _rate_limit_state.total_http_requests


def is_kis_request_budget_reached() -> bool:
    return _rate_limit_state.request_budget_reached


def mark_request_budget_reached() -> None:
    with _rate_limit_state._lock:
        _rate_limit_state.request_budget_reached = True


def is_rate_limit_msg(msg_cd: Any) -> bool:
    return str(msg_cd or "").strip().upper() == KIS_RATE_LIMIT_MSG_CD


def parse_rate_limit_from_response(res: requests.Response) -> tuple[bool, str | None]:
    """Detect EGW00201 from HTTP body without logging secrets."""
    try:
        data = res.json()
    except Exception:
        return False, None
    if not isinstance(data, dict):
        return False, None
    if is_rate_limit_msg(data.get("msg_cd")):
        return True, str(data.get("msg1") or "")[:500]
    return False, None


class _RollingWindowLimiter:
    """Cap requests per rolling 1-second window (process-wide)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window: deque[float] = deque()
        self._max_per_second = 1

    def configure(self, max_rps: float) -> None:
        self._max_per_second = max(1, int(max_rps) if max_rps >= 1 else 1)

    def acquire_slot(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._window and now - self._window[0] >= 1.0:
                    self._window.popleft()
                if len(self._window) < self._max_per_second:
                    self._window.append(now)
                    return
                wait = 1.0 - (now - self._window[0]) + 0.001
            time.sleep(min(max(wait, 0.01), 1.0))

    @property
    def max_per_second(self) -> int:
        return self._max_per_second


class _RateLimitState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.halted = False
            self.circuit_breaker_triggered = False
            self.rate_limit_error_count = 0
            self.retry_count = 0
            self.total_http_requests = 0
            self.actual_max_requests_in_rolling_1s = 0
            self._recent_request_times: deque[float] = deque()
            self.affected_tr_ids: set[str] = set()
            self.first_error_logged = False
            self.halt_summary_logged = False
            self.last_msg1: str | None = None
            self.request_budget_reached = False

    def _note_http_request(self) -> None:
        now = time.monotonic()
        self.total_http_requests += 1
        self._recent_request_times.append(now)
        while self._recent_request_times and now - self._recent_request_times[0] >= 1.0:
            self._recent_request_times.popleft()
        count = len(self._recent_request_times)
        if count > self.actual_max_requests_in_rolling_1s:
            self.actual_max_requests_in_rolling_1s = count

    def on_http_sent(self) -> None:
        with self._lock:
            self._note_http_request()

    def record_rate_limit(self, *, tr_id: str, msg1: str | None = None, retried: bool = False) -> None:
        with self._lock:
            self.rate_limit_error_count += 1
            if retried:
                self.retry_count += 1
            if tr_id:
                self.affected_tr_ids.add(tr_id)
            if msg1:
                self.last_msg1 = msg1[:500]
            if not self.first_error_logged:
                self.first_error_logged = True
                logger.warning(
                    "KIS rate limit msg_cd=%s tr_id=%s msg1=%s configured_rps=%s",
                    KIS_RATE_LIMIT_MSG_CD,
                    tr_id,
                    msg1,
                    configured_max_rps(),
                )
            halt_after = configured_halt_after()
            if self.rate_limit_error_count >= halt_after and not self.halted:
                self.halted = True
                self.circuit_breaker_triggered = True
                if not self.halt_summary_logged:
                    self.halt_summary_logged = True
                    logger.warning(
                        "KIS rate limit halt activated count=%s affected_tr_ids=%s "
                        "configured_rps=%s retry_count=%s total_http_requests=%s "
                        "actual_max_requests_in_rolling_1s=%s",
                        self.rate_limit_error_count,
                        sorted(self.affected_tr_ids)[:20],
                        configured_max_rps(),
                        self.retry_count,
                        self.total_http_requests,
                        self.actual_max_requests_in_rolling_1s,
                    )

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "halted": self.halted,
                "circuit_breaker_triggered": self.circuit_breaker_triggered,
                "rate_limit_error_count": self.rate_limit_error_count,
                "retry_count": self.retry_count,
                "affected_tr_ids": sorted(self.affected_tr_ids),
                "configured_rps": configured_max_rps(),
                "actual_max_requests_in_rolling_1s": self.actual_max_requests_in_rolling_1s,
                "total_http_requests": self.total_http_requests,
                "configured_max_retries": configured_max_retries(),
                "configured_backoff_sec": configured_backoff_sec(),
                "configured_halt_after": configured_halt_after(),
                "configured_max_requests_per_run": configured_max_requests_per_run(),
                "kis_requests_used": self.total_http_requests,
                "request_budget_reached": self.request_budget_reached,
                "last_msg_cd": KIS_RATE_LIMIT_MSG_CD if self.rate_limit_error_count else None,
                "last_msg1": self.last_msg1,
            }


_rolling_limiter = _RollingWindowLimiter()
_rate_limit_state = _RateLimitState()
_rolling_limiter.configure(configured_max_rps())


def reset_kis_rate_limit_state() -> None:
    _rate_limit_state.reset()
    _rolling_limiter.configure(configured_max_rps())


def is_kis_rate_limit_halted() -> bool:
    return _rate_limit_state.halted


def record_kis_rate_limit_error(*, tr_id: str, msg1: str | None = None, retried: bool = False) -> None:
    _rate_limit_state.record_rate_limit(tr_id=tr_id, msg1=msg1, retried=retried)


def kis_rate_limit_observability() -> dict[str, Any]:
    return _rate_limit_state.summary()


def rate_limiter_min_interval() -> float:
    return 1.0 / configured_max_rps()


def kis_http_request(
    method: str,
    url: str,
    *,
    tr_id: str = "",
    **kwargs: Any,
) -> requests.Response | None:
    """
    Single entry for outbound KIS HTTP. Rolling 1s cap + per-run budget + halt.
    """
    if _rate_limit_state.halted or _rate_limit_state.request_budget_reached:
        return None
    budget = configured_max_requests_per_run()
    with _rate_limit_state._lock:
        if _rate_limit_state.total_http_requests >= budget:
            _rate_limit_state.request_budget_reached = True
            return None
    _rolling_limiter.acquire_slot()
    if _rate_limit_state.halted or _rate_limit_state.request_budget_reached:
        return None
    with _rate_limit_state._lock:
        if _rate_limit_state.total_http_requests >= budget:
            _rate_limit_state.request_budget_reached = True
            return None
        _rate_limit_state._note_http_request()
        if _rate_limit_state.total_http_requests >= budget:
            _rate_limit_state.request_budget_reached = True
    return requests.request(method, url, **kwargs)


# Backward-compatible alias used by kis_client during migration
def kis_rate_limiter_acquire() -> None:
    """Deprecated spacing acquire — prefer kis_http_request."""
    if _rate_limit_state.halted:
        return
    _rolling_limiter.acquire_slot()
