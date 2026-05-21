"""API 키 로드 — 로컬 .env / CI secrets (os.environ)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DOTENV_DONE = False


def ensure_env_loaded() -> None:
    """python-dotenv 있으면 load_dotenv(), 없으면 안내만."""
    global _DOTENV_DONE
    if _DOTENV_DONE:
        return
    _DOTENV_DONE = True
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        logger.warning(
            "python-dotenv 미설치 — API 키는 OS 환경변수만 사용합니다. "
            "설치: pip install python-dotenv"
        )


def getenv(name: str) -> str:
    ensure_env_loaded()
    return os.getenv(name, "").strip()
