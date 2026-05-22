"""섹터별 병렬 시세 수집·1차 후보 선별."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from data.kr_watchlist import iter_watchlist_entries, watchlist_sectors_meta

from .ai_judge import RULE_CANDIDATE_MAX
from .market_data import collect_sector_market_data
from .sector_mood import judge_sector_mood, judge_single_sector_mood
from .watchlist_pick import pick_sector_candidates

logger = logging.getLogger("kr_intraday.sector_scan")

_PARALLEL_WORKERS = 5
_SECTOR_PICK_LIMIT = 2


@dataclass
class SectorScanResult:
    sector_key: str
    sector_name: str
    sector_order: int = 0
    ok: bool = True
    error: str | None = None
    stocks: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    sector_mood: str = "neutral"


@dataclass
class MergedSectorScan:
    stocks: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    sector_mood: dict[str, str] = field(default_factory=dict)
    sector_results: list[SectorScanResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _entries_for_sector(sector_key: str, allow_tickers: set[str] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in iter_watchlist_entries():
        if entry.get("sector_key") != sector_key:
            continue
        ticker = str(entry.get("ticker", "")).zfill(6)
        if not ticker:
            continue
        if allow_tickers is not None and ticker not in allow_tickers:
            continue
        out.append(entry)
    return out


def scan_one_sector(
    sector_meta: dict[str, Any],
    *,
    slot: str,
    live: bool,
    allow_tickers: set[str] | None,
) -> SectorScanResult:
    """단일 섹터: 시세 수집 → 분위기 → 1차 후보 (실패해도 예외 전파 안 함)."""
    sector_key = str(sector_meta.get("sector_key", ""))
    sector_name = str(sector_meta.get("sector_name", ""))
    sector_order = int(sector_meta.get("order", 0))
    base = SectorScanResult(
        sector_key=sector_key,
        sector_name=sector_name,
        sector_order=sector_order,
    )

    try:
        entries = _entries_for_sector(sector_key, allow_tickers)
        if not entries:
            base.ok = False
            base.error = "관심종목 0건"
            logger.warning("[%s] %s", sector_name, base.error)
            return base

        stocks = collect_sector_market_data(entries, slot, live=live)
        base.stocks = stocks

        if live and stocks and not any(s.get("data_complete") for s in stocks):
            base.ok = False
            base.error = "데이터 수집 실패"
            logger.error("[%s] 데이터 수집 실패: 유효 시세 0건", sector_name)
            return base

        mood_value = judge_single_sector_mood(stocks, sector_name)
        base.sector_mood = mood_value
        mood_map = {sector_name: mood_value}
        picks = pick_sector_candidates(
            stocks,
            mood_map,
            slot=slot,
            limit=_SECTOR_PICK_LIMIT,
        )
        base.candidates = picks
        logger.info(
            "[%s] sector scan ok stocks=%d candidates=%d mood=%s",
            sector_name,
            len(stocks),
            len(picks),
            mood_value,
        )
        return base
    except Exception as exc:
        base.ok = False
        base.error = f"데이터 수집 실패: {exc}"
        try:
            logger.error("[%s] %s", sector_name, base.error, exc_info=live)
        except Exception:
            pass
        return base


def scan_temp_watch_bucket(
    *,
    slot: str,
    live: bool,
    allow_tickers: set[str] | None,
) -> SectorScanResult | None:
    """임시 관찰 후보 (kr_watchlist 미수정)."""
    try:
        from data.candidates.temporary_watch import temp_candidates_as_watchlist_entries
    except ImportError:
        return None
    entries = temp_candidates_as_watchlist_entries()
    if allow_tickers is not None:
        entries = [e for e in entries if str(e.get("ticker", "")).zfill(6) in allow_tickers]
    if not entries:
        return None
    meta = {
        "sector_key": "temp_watch",
        "sector_name": "임시 관찰",
        "order": 99,
    }
    return scan_one_sector(meta, slot=slot, live=live, allow_tickers=allow_tickers)


def run_sector_scan_parallel(
    *,
    slot: str,
    live: bool = False,
    tickers: list[str] | None = None,
    max_workers: int = _PARALLEL_WORKERS,
    include_temp_watch: bool = False,
) -> list[SectorScanResult]:
    """관심 5섹터 병렬 스캔."""
    allow = {str(t).zfill(6) for t in tickers} if tickers else None
    metas = watchlist_sectors_meta()
    results: list[SectorScanResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                scan_one_sector,
                meta,
                slot=slot,
                live=live,
                allow_tickers=allow,
            ): meta
            for meta in metas
        }
        for future in as_completed(futures):
            meta = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                name = str(meta.get("sector_name", ""))
                logger.error("[%s] 데이터 수집 실패: %s", name, exc)
                results.append(
                    SectorScanResult(
                        sector_key=str(meta.get("sector_key", "")),
                        sector_name=name,
                        sector_order=int(meta.get("order", 0)),
                        ok=False,
                        error=f"데이터 수집 실패: {exc}",
                    )
                )

    if include_temp_watch:
        temp_res = scan_temp_watch_bucket(
            slot=slot, live=live, allow_tickers=allow
        )
        if temp_res is not None:
            results.append(temp_res)

    results.sort(key=lambda r: r.sector_order)
    try:
        from utils.safe_stdio import ensure_stdio

        ensure_stdio()
    except ImportError:
        pass
    return results


def merge_sector_scan_results(
    sector_results: list[SectorScanResult],
    *,
    slot: str,
) -> MergedSectorScan:
    """섹터별 결과 병합 → 전체 시세·분위기·DeepSeek 배치용 후보(최대 7)."""
    merged = MergedSectorScan(sector_results=list(sector_results))
    all_candidates: list[dict[str, Any]] = []

    for res in sector_results:
        if not res.ok:
            note = f"[{res.sector_name}] {res.error or '데이터 수집 실패'}"
            merged.notes.append(note)
            continue
        merged.stocks.extend(res.stocks)
        all_candidates.extend(res.candidates)

    if merged.stocks:
        merged.sector_mood = judge_sector_mood(merged.stocks, slot)
    else:
        from data.kr_watchlist import watchlist_sector_labels

        merged.sector_mood = {label: "neutral" for label in watchlist_sector_labels()}

    all_candidates.sort(
        key=lambda r: float(r.get("_pick_score") or 0),
        reverse=True,
    )
    merged.candidates = all_candidates[:RULE_CANDIDATE_MAX]

    logger.info(
        "[KR INTRADAY] merge sectors=%d stocks=%d batch_candidates=%d failed_sectors=%d",
        len(sector_results),
        len(merged.stocks),
        len(merged.candidates),
        sum(1 for r in sector_results if not r.ok),
    )
    return merged
