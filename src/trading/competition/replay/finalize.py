"""Campaign end — mark-to-market at last session close (no forced sells)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from src.trading.competition.constants import TEAM_IDS
from src.trading.competition.replay.market_data import close_price_krw
from src.trading.competition.replay.period import FULL_AUDIT_END, FULL_AUDIT_START
from src.trading.competition.runtime import COMPETITION_ROOT

CAMPAIGNS_ROOT = COMPETITION_ROOT / "replay" / "campaigns"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_campaign_manifest(campaign_id: str) -> dict[str, Any]:
    return _read_json(CAMPAIGNS_ROOT / campaign_id / "manifest.json")


def is_campaign_ended(campaign_id: str | None) -> bool:
    if not campaign_id:
        return False
    manifest = load_campaign_manifest(campaign_id)
    return manifest.get("competition_status") == "ended"


def mark_accounts_to_market(
    accounts: dict[str, dict[str, Any]],
    valuation_date: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Revalue open positions at session close; do not create sell trades."""
    out = copy.deepcopy(accounts)
    meta: dict[str, Any] = {
        "valuation_date": valuation_date,
        "valuation_method": "session_close_or_last_known",
        "missing_close_prices": [],
        "forced_liquidation": False,
    }
    for tid in TEAM_IDS:
        acc = out.get(tid) or {}
        cash = int(acc.get("cash_krw") or 0)
        pos_val = 0
        for pos in acc.get("positions") or []:
            qty = int(pos.get("quantity") or 0)
            if qty <= 0:
                continue
            ticker = str(pos.get("ticker") or "").zfill(6)
            avg = int(pos.get("avg_price_krw") or 0)
            px, err = close_price_krw(ticker, valuation_date)
            if not px:
                px = int(pos.get("current_price_krw") or avg)
                if px:
                    meta["missing_close_prices"].append(
                        {"team_id": tid, "ticker": ticker, "fallback_price": px, "error": err}
                    )
                else:
                    meta["missing_close_prices"].append(
                        {"team_id": tid, "ticker": ticker, "error": err or "no_price"}
                    )
            pos["current_price_krw"] = px
            cost = avg * qty
            market = px * qty
            pos["eval_pnl_krw"] = market - cost
            pos["eval_return_pct"] = round((px - avg) / avg * 100, 2) if avg else 0.0
            pos_val += market
        acc["cash_krw"] = cash
        acc["total_assets_krw"] = cash + pos_val
        acc["status"] = "ended_mark_to_market"
        out[tid] = acc
    return out, meta


def finalize_full_audit_campaign(
    campaign_id: str,
    accounts: dict[str, dict[str, Any]],
    *,
    last_trading_date: str,
    run_ids: list[str],
) -> dict[str, Any]:
    """Mark competition ended and persist final account snapshot on campaign manifest."""
    final_accounts, valuation_meta = mark_accounts_to_market(accounts, last_trading_date)
    camp_dir = CAMPAIGNS_ROOT / campaign_id
    manifest = _read_json(camp_dir / "manifest.json")
    manifest.update(
        {
            "competition_status": "ended",
            "decisions_frozen": True,
            "period_start": FULL_AUDIT_START,
            "period_end": FULL_AUDIT_END,
            "final_valuation_date": last_trading_date,
            "final_accounts": final_accounts,
            "final_valuation": valuation_meta,
            "ended_at_trading_date": last_trading_date,
            "run_ids": run_ids,
        }
    )
    (camp_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (camp_dir / "final_accounts.json").write_text(
        json.dumps(
            {"accounts": final_accounts, "valuation": valuation_meta},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest
