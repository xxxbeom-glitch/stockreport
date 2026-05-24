"""Process-wide KIS REST rate limiting and EGW00201 circuit breaker."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

KIS_RATE_LIMIT_MSG_CD = "EGW00201"

_DEFAULT_RPS = 8.0
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_BACKOFF_SEC = 0.6
_DEFAULT_HALT_AFTER = 10


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


class _GlobalRateLimiter:
    """Thread-safe minimum spacing between KIS HTTP calls in this process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_at = 0.0

    def configure(self, max_rps: float) -> None:
        self._max_rps = max(0.1, max_rps)
        self._min_interval = 1.0 / self._max_rps

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_at)
            if wait > 0:
                time.sleep(wait)
            self._last_at = time.monotonic()

    @property
    def min_interval(self) -> float:
        return self._min_interval


class _RateLimitState:
    """Aggregate EGW00201 occurrences; halt bulk calls after threshold."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.halted = False
            self.rate_limit_error_count = 0
            self.retry_count = 0
            self.affected_tr_ids: set[str] = set()
            self.first_error_logged = False
            self.last_msg1: str | None = None

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
                logger.warning(
                    "KIS rate limit halt activated count=%s affected_tr_ids=%s configured_rps=%s retry_count=%s",
                    self.rate_limit_error_count,
                    sorted(self.affected_tr_ids)[:20],
                    configured_max_rps(),
                    self.retry_count,
                )

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "halted": self.halted,
                "rate_limit_error_count": self.rate_limit_error_count,
                "retry_count": self.retry_count,
                "affected_tr_ids": sorted(self.affected_tr_ids),
                "configured_rps": configured_max_rps(),
                "configured_max_retries": configured_max_retries(),
                "configured_backoff_sec": configured_backoff_sec(),
                "configured_halt_after": configured_halt_after(),
                "last_msg_cd": KIS_RATE_LIMIT_MSG_CD if self.rate_limit_error_count else None,
                "last_msg1": self.last_msg1,
            }


_rate_limiter = _GlobalRateLimiter()
_rate_limit_state = _RateLimitState()
_rate_limiter.configure(configured_max_rps())


def reset_kis_rate_limit_state() -> None:
    _rate_limit_state.reset()
    _rate_limiter.configure(configured_max_rps())


def kis_rate_limiter_acquire() -> None:
    if _rate_limit_state.halted:
        return
    _rate_limiter.acquire()


def is_kis_rate_limit_halted() -> bool:
    return _rate_limit_state.halted


def record_kis_rate_limit_error(*, tr_id: str, msg1: str | None = None, retried: bool = False) -> None:
    _rate_limit_state.record_rate_limit(tr_id=tr_id, msg1=msg1, retried=retried)


def kis_rate_limit_observability() -> dict[str, Any]:
    return _rate_limit_state.summary()


def rate_limiter_min_interval() -> float:
    return _rate_limiter.min_interval


def is_rate_limit_msg(msg_cd: Any) -> bool:
    return str(msg_cd or "").strip().upper() == KIS_RATE_LIMIT_MSG_CD
