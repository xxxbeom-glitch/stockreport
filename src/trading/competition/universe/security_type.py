"""Security type classification helpers."""

from __future__ import annotations

import re

# Known preferred tickers (KRX) — not imported from mock_trading/watchlist pools
KNOWN_PREFERRED_TICKERS: frozenset[str] = frozenset(
    {
        "103595",
        "009155",
    }
)

_PREFERRED_NAME_FALSE_POSITIVES: frozenset[str] = frozenset({"대우"})

_ETF_PATTERN = re.compile(
    r"ETF|ETN|리츠|REIT|SPAC|스팩|인프라\s*펀드|레버",
    re.IGNORECASE,
)
_PREFERRED_SUFFIX = re.compile(r"우$|우B$|우C$|1우$|2우$|3우$")


def is_preferred_stock(name: str, ticker: str) -> bool:
    code = str(ticker or "").strip().zfill(6)
    if code in KNOWN_PREFERRED_TICKERS:
        return True
    n = str(name or "").strip()
    if not n or n in _PREFERRED_NAME_FALSE_POSITIVES:
        return False
    if len(n) >= 4 and n.endswith("우"):
        return True
    return False


def classify_security_type(name: str, ticker: str = "") -> str:
    n = (name or "").strip()
    if not n:
        return "unknown"
    if is_preferred_stock(n, ticker):
        return "preferred"
    if _ETF_PATTERN.search(n):
        if "ETN" in n.upper():
            return "etn"
        if re.search(r"리츠|REIT", n, re.I):
            return "reit"
        if re.search(r"SPAC|스팩", n, re.I):
            return "spac"
        return "etf"
    return "common"
