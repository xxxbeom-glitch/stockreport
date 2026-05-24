"""Safe pykrx wrappers — avoid uncaught JSON errors when KRX login/HTML fails."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from typing import Any, Callable

_PYKRX_LOGIN_MARKERS = (
    "KRX_ID",
    "KRX_PW",
    "KRX 로그인",
    "krx 로그인",
)


def krx_credentials_configured() -> bool:
    return bool((os.getenv("KRX_ID") or "").strip() and (os.getenv("KRX_PW") or "").strip())


@contextlib.contextmanager
def _suppress_pykrx_stdio() -> Any:
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        yield
    finally:
        sys.stdout, sys.stderr = out, err


def classify_pykrx_error(exc: BaseException) -> str:
    msg = str(exc)
    if any(m in msg for m in _PYKRX_LOGIN_MARKERS):
        return "krx_credentials_missing"
    if isinstance(exc, json.JSONDecodeError):
        return "krx_empty_or_non_json_response"
    name = type(exc).__name__
    if name in ("JSONDecodeError", "ValueError"):
        return "krx_parse_error"
    return f"pykrx_{name}"


def safe_pykrx_call(
    label: str,
    fn: Callable[[], Any],
    *,
    allow_empty_frame: bool = True,
) -> tuple[Any | None, dict[str, Any]]:
    """
    Run a pykrx callable; never raise JSONDecodeError to callers.
    Returns (result, meta) where meta has ok, error_code, detail.
    """
    meta: dict[str, Any] = {"provider": "pykrx", "call": label, "ok": False}
    try:
        with _suppress_pykrx_stdio():
            result = fn()
    except Exception as exc:
        code = classify_pykrx_error(exc)
        meta.update(
            {
                "ok": False,
                "error_code": code,
                "detail": str(exc)[:500],
                "krx_login_required": code == "krx_credentials_missing",
            }
        )
        return None, meta

    if result is None:
        meta.update({"ok": False, "error_code": "pykrx_empty", "detail": "null_result"})
        return None, meta

    try:
        length = len(result)
    except TypeError:
        length = 1 if result else 0

    if length == 0 and not allow_empty_frame:
        meta.update({"ok": False, "error_code": "pykrx_empty_frame", "detail": "empty_frame"})
        return None, meta

    meta["ok"] = True
    meta["rows"] = length
    return result, meta
