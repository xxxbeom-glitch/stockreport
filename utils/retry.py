"""Retry decorator with short bounded waits."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def retry(max_attempts: int = 2, delay_sec: float = 1.0) -> Callable[[Callable[..., T]], Callable[..., T | dict[str, Any]]]:
    """Retry callable and return fallback dict on repeated failures."""

    def decorator(func: Callable[..., T]) -> Callable[..., T | dict[str, Any]]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T | dict[str, Any]:
            last_error: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: PERF203
                    last_error = exc
                    print(f"[WARN] retry {attempt}/{max_attempts} failed in {func.__name__}: {exc}")
                    if attempt < max_attempts:
                        time.sleep(delay_sec)
            return {"ok": False, "error": f"{func.__name__} failed after retry: {last_error}"}

        return wrapper

    return decorator

