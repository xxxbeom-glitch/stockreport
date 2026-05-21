"""Process stdout/stderr safety (CI tee, threaded pykrx redirect)."""

from __future__ import annotations

import logging
import sys
from typing import TextIO


def ensure_stdio() -> None:
    """Replace closed or broken sys.stdout/sys.stderr with originals."""
    for name in ("stdout", "stderr"):
        current = getattr(sys, name, None)
        original = getattr(sys, f"__{name}__", None)
        if original is None:
            continue
        try:
            if current is None or getattr(current, "closed", False):
                setattr(sys, name, original)
        except Exception:
            setattr(sys, name, original)


def _stream(prefer_stderr: bool = False) -> TextIO:
    ensure_stdio()
    return sys.__stderr__ if prefer_stderr else sys.__stdout__


def setup_logging(*, level: int = logging.INFO) -> None:
    """StreamHandler on sys.__stderr__ only (never a closed redirect target)."""
    ensure_stdio()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    handler = logging.StreamHandler(sys.__stderr__)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)


def safe_print(*args, **kwargs) -> None:
    """print() that survives closed stdout (e.g. after threaded redirect)."""
    ensure_stdio()
    file = kwargs.get("file")
    prefer_stderr = file is sys.stderr or file is sys.__stderr__
    if file is None:
        kwargs["file"] = _stream(prefer_stderr=prefer_stderr)
    try:
        print(*args, **kwargs)
    except (ValueError, OSError):
        try:
            kwargs["file"] = sys.__stderr__ if prefer_stderr else sys.__stdout__
            print(*args, **kwargs)
        except Exception:
            pass


def safe_print_exception(exc: BaseException, *, prefix: str = "") -> None:
    ensure_stdio()
    import traceback

    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    msg = "".join(lines)
    if prefix:
        msg = f"{prefix}\n{msg}"
    try:
        sys.__stderr__.write(msg)
        sys.__stderr__.flush()
    except Exception:
        pass
