"""Slack market report sender (single message + briefing link button)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

import config

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"

KR_REPORT_TYPES = frozenset({"kr_during", "kr_close_us_before", "kr_before", "kr_after"})
US_REPORT_TYPES = frozenset({"us_during", "us_close_kr_before", "us_before", "us_after"})

KR_SLACK_CHANNEL_TYPES = frozenset({"kr_during", "kr_close_us_before"})
US_SLACK_CHANNEL_TYPES = frozenset({"us_during", "us_close_kr_before"})

REPORT_TYPE_DESC: dict[str, str] = {
    "us_during": "미국 장중 브리핑",
    "us_close_kr_before": "미국 마감 · 국장 장전",
    "kr_during": "한국 장중 브리핑",
    "kr_close_us_before": "한국 마감 · 미국 장전",
    "kr_before": "국장 장전",
    "kr_after": "국장 장후",
    "us_before": "미장 장전",
    "us_after": "미장 장후",
    "weekly": "주간 종합",
}

INDICATOR_LABELS: dict[str, str] = {
    "dollar_index": "달러인덱스",
    "us10y": "미국10년금리",
    "vix": "공포지수(VIX)",
    "wti": "국제유가(WTI)",
    "copper": "구리",
}

WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")

PHASE_LABELS: dict[str, str] = {
    "risk_off": "위험회피",
    "risk-off": "위험회피",
    "bearish": "약세",
    "weak": "약세",
    "neutral": "중립",
    "sideways": "중립",
    "bullish": "강세",
    "risk_on": "강세",
    "risk-on": "강세",
    "strong": "강세",
}


def resolve_slack_channel(report_type: str) -> str | None:
    """Pick Slack channel ID from report_type."""
    if report_type in KR_SLACK_CHANNEL_TYPES:
        return config.SLACK_CHANNEL_KR or os.getenv("SLACK_CHANNEL_KR", "") or None
    if report_type in US_SLACK_CHANNEL_TYPES:
        return config.SLACK_CHANNEL_US or os.getenv("SLACK_CHANNEL_US", "") or None
    if report_type in KR_REPORT_TYPES or report_type.startswith("kr"):
        return config.SLACK_CHANNEL_KR or os.getenv("SLACK_CHANNEL_KR", "") or None
    if report_type in US_REPORT_TYPES or report_type.startswith("us"):
        return config.SLACK_CHANNEL_US or os.getenv("SLACK_CHANNEL_US", "") or None
    return config.SLACK_CHANNEL_KR or os.getenv("SLACK_CHANNEL_KR", "") or None


def _is_kr_report(report_type: str) -> bool:
    if report_type in KR_REPORT_TYPES:
        return True
    if report_type in US_REPORT_TYPES:
        return False
    return report_type.startswith("kr")


def _arrow(is_up: Any, change: str = "") -> str:
    if change in ("", "N/A", None):
        return " "
    return "▲" if is_up else "▼"


def _safe_str(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _volume_emoji(ratio: float) -> str:
    if ratio >= config.VOLUME_FIRE:
        return "🔥"
    if ratio >= config.VOLUME_BOLT:
        return "⚡"
    return "💵"


def _parse_ratio(value: Any) -> float:
    try:
        return float(str(value).replace("배", "").replace("x", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _enrich_report_data(report_data: dict[str, Any], report_type: str) -> dict[str, Any]:
    data = dict(report_data)
    if not data.get("sector_top_stocks") and _is_kr_report(report_type):
        try:
            from data.kr_market import get_sector_top_stocks

            data["sector_top_stocks"] = get_sector_top_stocks(3)
        except Exception:
            data.setdefault("sector_top_stocks", {})

    if not data.get("volume_leaders_ranked"):
        try:
            if _is_kr_report(report_type):
                from data.kr_market import get_top_volume_kr

                data["volume_leaders_ranked"] = get_top_volume_kr(5) or []
            else:
                from data.us_market import get_top_volume_us

                data["volume_leaders_ranked"] = get_top_volume_us(5) or []
        except Exception:
            data.setdefault("volume_leaders_ranked", [])

    if not data.get("watchlist_stocks"):
        stocks: list[dict[str, Any]] = []
        for theme, tickers in config.KR_WATCHLIST.items():
            if not _is_kr_report(report_type):
                break
            for ticker, name in tickers.items():
                stocks.append({"ticker": ticker, "name": name, "market": "KR", "theme": theme})
        if not _is_kr_report(report_type):
            for theme, tickers in config.US_WATCHLIST.items():
                for ticker, name in tickers.items():
                    stocks.append({"ticker": ticker, "name": name, "market": "US", "theme": theme})
        data["watchlist_stocks"] = stocks

    return data


def _phase_display(phase: Any) -> str:
    key = str(phase or "중립").strip().lower()
    return PHASE_LABELS.get(key, str(phase or "중립"))


def _header_line(report_type: str) -> tuple[str, str]:
    now = datetime.now()
    weekday = WEEKDAY_KO[now.weekday()]
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%Y-%m-%d")
    desc = REPORT_TYPE_DESC.get(report_type, report_type)
    if report_type in ("us_close_kr_before", "kr_during", "kr_before", "kr_after"):
        market_line = f"한국시장 | {desc}"
    elif report_type in ("kr_close_us_before", "us_during", "us_before", "us_after"):
        market_line = f"미국시장 | {desc}"
    elif _is_kr_report(report_type):
        market_line = f"한국시장 | {desc}"
    else:
        market_line = f"미국시장 | {desc}"
    title = f"📅 마켓 브리핑 | {date_str} {weekday}요일 {time_str}"
    return title, market_line


def _compact_index(label: str, row: dict[str, Any] | None) -> str:
    row = row or {}
    value = _safe_str(row.get("value"))
    change = _safe_str(row.get("change"))
    mark = _arrow(row.get("is_up"), change)
    if change in ("N/A", ""):
        return f"{label} {value}"
    return f"{label} {value} {mark}{change}"


def build_summary_message(report_data: dict[str, Any], report_type: str) -> str:
    """Build a single Slack text summary (indices + phase)."""
    title, market_line = _header_line(report_type)
    phase = _phase_display(report_data.get("market_phase"))
    summary = _safe_str(report_data.get("one_line_summary"))
    indices = report_data.get("indices") or {}

    line_kr = "  ".join(
        [
            _compact_index("KOSPI", indices.get("KOSPI")),
            _compact_index("KOSDAQ", indices.get("KOSDAQ")),
        ]
    )
    line_us = "  ".join(
        [
            _compact_index("S&P500", indices.get("S&P500") or indices.get("S&P 500")),
            _compact_index("NASDAQ", indices.get("NASDAQ")),
        ]
    )

    lines = [
        title,
        market_line,
        "",
        "오늘 시장은?",
        f"{phase} — {summary}",
        "",
        line_kr,
        line_us,
    ]
    return "\n".join(lines)


def _briefing_blocks(text: str, briefing_url: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]
    if briefing_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "브리핑 보기", "emoji": True},
                        "url": briefing_url,
                        "action_id": "open_briefing_html",
                    }
                ],
            }
        )
    return blocks


def _index_line(label: str, row: dict[str, Any] | None) -> str:
    row = row or {}
    value = _safe_str(row.get("value"))
    change = _safe_str(row.get("change"))
    mark = _arrow(row.get("is_up"), change)
    return f"{label:<8}  {value:>12}    {mark} {change}"


def _indicator_line(
    key: str,
    indicators: dict[str, Any],
    macro_comments: dict[str, str],
) -> str:
    label = INDICATOR_LABELS.get(key, key)
    row = indicators.get(key) or {}
    value = _safe_str(row.get("value"))
    change = _safe_str(row.get("change"))
    mark = _arrow(row.get("is_up"), change)
    comment = _safe_str(macro_comments.get(key, ""), "")
    pad_label = label.ljust(12)
    if comment and comment != "N/A":
        return f"{pad_label}  {value:>8}   {mark} {change:>8}   {comment}"
    return f"{pad_label}  {value:>8}   {mark} {change:>8}"


def build_msg1(report_data: dict[str, Any], report_type: str) -> str:
    title, market_line = _header_line(report_type)
    phase = _safe_str(report_data.get("market_phase"), "중립")
    summary = _safe_str(report_data.get("one_line_summary"))
    indices = report_data.get("indices") or {}
    indicators = report_data.get("indicators") or report_data.get("market_indicators") or {}
    macro_comments = report_data.get("macro_comments") or {}

    lines = [
        title,
        market_line,
        "",
        "오늘 시장은?",
        f"{phase} — {summary}",
        "",
        "──────────────────",
        _index_line("KOSPI", indices.get("KOSPI")),
        _index_line("KOSDAQ", indices.get("KOSDAQ")),
        _index_line("S&P500", indices.get("S&P500") or indices.get("S&P 500")),
        _index_line("NASDAQ", indices.get("NASDAQ")),
        "",
        _indicator_line("dollar_index", indicators, macro_comments),
        _indicator_line("us10y", indicators, macro_comments),
        _indicator_line("vix", indicators, macro_comments),
        _indicator_line("wti", indicators, macro_comments),
        _indicator_line("copper", indicators, macro_comments),
        "──────────────────",
    ]
    pdf = report_data.get("pdf_url")
    if pdf:
        lines.extend(["", f"📎 리포트: {pdf}"])
    return "\n".join(lines)


def _format_stock_chip(stock: dict[str, Any]) -> str:
    name = _safe_str(stock.get("name"))
    change = _safe_str(stock.get("change") or stock.get("change_rate"))
    if isinstance(stock.get("change_rate"), (int, float)):
        pct = float(stock["change_rate"])
        change = f"{pct:+.2f}%"
    is_up = stock.get("is_up")
    if is_up is None and change not in ("N/A", ""):
        is_up = not str(change).strip().startswith("-")
    mark = _arrow(is_up, change)
    return f"{name} {mark}{change}"


def _sector_block(sector_name: str, stocks: list[dict[str, Any]]) -> list[str]:
    if not stocks:
        return []
    chips = " · ".join(_format_stock_chip(s) for s in stocks[:3])
    return [f"  {sector_name}  {chips}"]


def build_msg2(report_data: dict[str, Any], report_type: str) -> str:
    sector_flow = report_data.get("sector_flow") or {}
    hot = sector_flow.get("hot") or []
    cold = sector_flow.get("cold") or []
    sector_top = report_data.get("sector_top_stocks") or {}

    lines = [
        "──────────────────",
        "오늘의 섹터 동향",
        "──────────────────",
    ]

    if hot:
        lines.append(f"▲ 상승   {', '.join(hot[:8])}")
        lines.append("")
        for name in hot[:5]:
            lines.extend(_sector_block(name, sector_top.get(name, [])))
    else:
        lines.append("▲ 상승   N/A")

    lines.append("")
    if cold:
        lines.append(f"▼ 하락   {', '.join(cold[:8])}")
        lines.append("")
        for name in cold[:5]:
            lines.extend(_sector_block(name, sector_top.get(name, [])))
    else:
        lines.append("▼ 하락   N/A")

    leaders = report_data.get("volume_leaders_ranked") or []
    if not leaders:
        themes = report_data.get("top_themes") or []
        if themes:
            leaders = themes[0].get("volume_leaders") or []

    lines.extend(
        [
            "",
            "──────────────────",
            "거래대금 상위 종목",
            "──────────────────",
            "종목           현재가        등락률    평균대비",
        ]
    )

    for idx, row in enumerate(leaders[:5], start=1):
        name = _safe_str(row.get("name"))
        if _is_kr_report(report_type):
            price = row.get("price")
            if isinstance(price, (int, float)):
                price_txt = f"{int(price):,}원"
            else:
                price_txt = _safe_str(price)
        else:
            price_txt = _safe_str(row.get("price_fmt") or row.get("price_krw"))
            if isinstance(row.get("price_krw"), (int, float)):
                price_txt = f"{int(row['price_krw']):,}원"

        change = _safe_str(row.get("change"))
        if not change or change == "N/A":
            cr = row.get("change_rate")
            if isinstance(cr, (int, float)):
                change = f"{cr:+.2f}%"

        ratio = _parse_ratio(row.get("volume_ratio") or row.get("ratio"))
        ratio_txt = f"{ratio:.1f}배" if ratio else "N/A"
        emoji = _volume_emoji(ratio) if ratio else ""
        lines.append(f"{idx}. {name:<10}  {price_txt:>12}  {change:>8}  {ratio_txt} {emoji}".rstrip())

    lines.append("──────────────────")
    return "\n".join(lines)


def build_msg3(report_data: dict[str, Any], report_type: str) -> str:
    lines = [
        "──────────────────",
        "관심 섹터 현황",
        "──────────────────",
    ]

    pipeline_stocks = {
        str(s.get("ticker", "")).zfill(6): s for s in (report_data.get("pipeline_watchlist") or [])
    }
    pipeline_stocks.update(
        {str(s.get("ticker", "")).upper(): s for s in (report_data.get("pipeline_watchlist") or [])}
    )

    if _is_kr_report(report_type):
        watchlist = config.KR_WATCHLIST
    else:
        watchlist = config.US_WATCHLIST

    for theme, tickers in watchlist.items():
        lines.append(theme)
        for ticker, name in tickers.items():
            key = ticker.zfill(6) if _is_kr_report(report_type) else ticker.upper()
            snap = pipeline_stocks.get(key) or pipeline_stocks.get(ticker) or {}
            change_rate = snap.get("change_rate")
            if isinstance(change_rate, (int, float)):
                change = f"{float(change_rate):+.2f}%"
                is_up = change_rate >= 0
            else:
                change = "N/A"
                is_up = None
            mark = _arrow(is_up, change)

            if _is_kr_report(report_type):
                price = snap.get("price")
                price_txt = f"{int(price):,}원" if isinstance(price, (int, float)) else "N/A"
            else:
                pk = snap.get("price_krw")
                price_txt = f"{int(pk):,}원" if isinstance(pk, (int, float)) else "N/A"

            ratio = _parse_ratio(snap.get("volume_ratio"))
            ratio_txt = f"{ratio:.1f}배" if ratio else "N/A"
            emoji = _volume_emoji(ratio) if ratio else ""
            display_name = _safe_str(snap.get("name"), name)
            lines.append(
                f"{display_name}  {price_txt}  {mark}{change}  |  거래량 {ratio_txt} {emoji}".rstrip()
            )
        lines.append("")

    lines.append("──────────────────")
    return "\n".join(lines)


def build_msg4(report_data: dict[str, Any], report_type: str) -> str:
    buys = report_data.get("buy_recommendations") or []
    if _is_kr_report(report_type) and buys:
        from data.kr_watchlist import filter_rows_to_watchlist

        buys = filter_rows_to_watchlist(buys)
    risk_warning = _safe_str(report_data.get("risk_warning"), "N/A")

    lines = [
        "──────────────────",
        "오늘의 매수 추천",
        "에이전트 5명 종합 매수 의견 종목",
        "──────────────────",
    ]

    if not buys:
        msg = report_data.get("recommendation_message") or "오늘은 관망이 답입니다."
        lines.extend(["", msg, "시장 전반이 불리한 환경이에요.", ""])
    else:
        numerals = "①②③④⑤"
        for idx, row in enumerate(buys[:5]):
            num = numerals[idx] if idx < len(numerals) else f"{idx + 1}."
            name = _safe_str(row.get("name"))
            price = _safe_str(row.get("price"))
            change = _safe_str(row.get("change_rate") or row.get("change"))
            emoji = _safe_str(row.get("volume_emoji"), "")
            strength = _safe_str(row.get("conclusion_strength"), "N/A")
            vol = _safe_str(row.get("volume_ratio"), "N/A")
            pos = _safe_str(row.get("position_52w"), "N/A")
            per = _safe_str(row.get("per"), "N/A")
            pbr = _safe_str(row.get("pbr"), "N/A")
            fo = _safe_str(row.get("foreign_ownership"), "N/A")
            reason = _safe_str(row.get("buy_reason"), "")
            verdict = _safe_str(row.get("verdict_comment"), "")

            lines.extend(
                [
                    "",
                    f"{num} {name} {price} {change} {emoji}".rstrip(),
                    f"체결강도 {strength}  |  거래량 {vol}",
                    f"52주 고점 대비 {pos}",
                    f"PER {per}  |  PBR {pbr}  |  외국인보유 {fo}",
                    "",
                    reason,
                ]
            )
            if verdict and verdict != "N/A":
                lines.append(verdict)

    lines.extend(
        [
            "",
            "──────────────────",
            "⚠️ 오늘 조심할 것",
            risk_warning,
            "",
            "※ 투자 참고용이며 손실 책임은",
            "  본인에게 있습니다.",
            "",
            "─",
            "PER: 주가가 비싼지 싼지. 낮을수록 저평가",
            "PBR: 1 이하면 회사 자산보다 싸게 거래중",
            "외국인보유: 높을수록 글로벌 큰손이 믿는 주식",
            "체결강도: 100% 이상이면 사는 사람이 더 많음",
            "🔥 거래량 30배 이상   ⚡ 거래량 15배 이상   💵 거래대금 상위",
            "──────────────────",
        ]
    )
    return "\n".join(lines)


def post_message(
    text: str,
    channel: str,
    thread_ts: str | None = None,
    *,
    blocks: list[dict[str, Any]] | None = None,
    retries: int = 1,
) -> dict[str, Any]:
    """Post one message via Slack chat.postMessage."""
    token = config.SLACK_BOT_TOKEN or os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "SLACK_BOT_TOKEN missing", "skipped": True}
    if not channel:
        return {"ok": False, "error": "Slack channel missing", "skipped": True}

    body: dict[str, Any] = {"channel": channel, "text": text}
    if blocks:
        body["blocks"] = blocks
    if thread_ts:
        body["thread_ts"] = thread_ts

    last_error = ""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                SLACK_POST_URL,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("ok"):
                return {"ok": True, "ts": payload.get("ts"), "response": payload}
            last_error = str(payload.get("error", "unknown_error"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        if attempt < retries:
            time.sleep(1.0)

    return {"ok": False, "error": last_error}


def _legacy_slack_skipped(report_type: str) -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": True,
        "reason": "legacy_report_slack_disabled",
        "report_type": report_type,
        "sent_count": 0,
        "errors": [],
    }


def send_market_report(
    report_data: dict[str, Any],
    report_type: str,
    pdf_url: str = "",
) -> dict[str, Any]:
    """Send one Slack message with summary text and optional briefing button."""
    if not config.legacy_report_slack_enabled():
        return _legacy_slack_skipped(report_type)

    token = config.SLACK_BOT_TOKEN or os.getenv("SLACK_BOT_TOKEN", "")
    channel = resolve_slack_channel(report_type) or ""
    if not token:
        return {
            "ok": False,
            "skipped": True,
            "sent_count": 0,
            "thread_ts": None,
            "channel": None,
            "errors": ["SLACK_BOT_TOKEN missing"],
        }
    if not channel:
        return {
            "ok": False,
            "skipped": True,
            "sent_count": 0,
            "thread_ts": None,
            "channel": None,
            "errors": [f"No Slack channel for report_type={report_type}"],
        }

    data = _enrich_report_data(report_data, report_type)
    briefing_url = pdf_url or str(data.get("pdf_url") or "")
    if briefing_url:
        data["pdf_url"] = briefing_url

    text = build_summary_message(data, report_type)
    blocks = _briefing_blocks(text, briefing_url)
    fallback = text if not briefing_url else f"{text}\n\n브리핑: {briefing_url}"

    result = post_message(fallback, channel, blocks=blocks, retries=1)
    errors: list[str] = []
    if not result.get("ok"):
        errors.append(str(result.get("error", "unknown")))

    return {
        "ok": bool(result.get("ok")),
        "sent_count": 1 if result.get("ok") else 0,
        "thread_ts": result.get("ts"),
        "channel": channel,
        "errors": errors,
        "briefing_url": briefing_url or None,
    }


def send_report(
    payload: dict[str, Any] | None = None,
    message: str | None = None,
    summary: str | None = None,
    report_type: str | None = None,
    pdf_url: str | None = None,
    send_at: int | None = None,
) -> dict[str, Any]:
    """Send market report summary via Slack Web API."""
    source = payload or {}
    rtype = report_type or source.get("report_type") or "unknown"
    url = pdf_url or source.get("pdf_url") or source.get("url") or ""

    if isinstance(send_at, (int, float)) or isinstance(source.get("send_at"), (int, float)):
        delay_ts = send_at if send_at is not None else source.get("send_at")
        delay = int(delay_ts - time.time())  # type: ignore[operator]
        if 0 < delay <= 600:
            time.sleep(delay)

    report = source.get("report_data")
    if isinstance(report, dict):
        data = dict(report)
    else:
        data = {
            "market_phase": "중립",
            "one_line_summary": summary or message or "N/A",
            "indices": {},
            "indicators": {},
            "macro_comments": {},
            "sector_flow": {"hot": [], "cold": []},
            "buy_recommendations": [],
            "risk_warning": "N/A",
        }
    if summary and not data.get("one_line_summary"):
        data["one_line_summary"] = summary
    return send_market_report(data, rtype, url)


def _kr_watchlist_intro_line() -> str:
    """실행 시각·workflow에 따른 첫 문장 (KST)."""
    slot = os.getenv("KR_BRIEFING_SLOT", "").strip().lower()
    if slot == "morning":
        return "오전 9시 기준 관심종목 리포트 전달드립니다."
    if slot == "afternoon":
        return "오후 5시 기준 관심종목 리포트 전달드립니다."
    if os.getenv("GITHUB_EVENT_NAME", "").strip() == "workflow_dispatch":
        return "관심종목 리포트 전달드립니다."

    try:
        from datetime import datetime, timedelta, timezone

        kst = datetime.now(timezone(timedelta(hours=9)))
        hour = kst.hour
        if 8 <= hour <= 10:
            return "오전 9시 기준 관심종목 리포트 전달드립니다."
        if 16 <= hour <= 18:
            return "오후 5시 기준 관심종목 리포트 전달드립니다."
    except Exception:
        pass
    return "관심종목 리포트 전달드립니다."


def build_kr_watchlist_report_slack_text(
    result: dict[str, Any],
    briefing_url: str = "",
) -> str:
    """사용자용 KR 관심종목 리포트 Slack 본문 (개발 검증 로그 아님)."""
    sectors = int(result.get("sectors") or 5)
    stocks = int(result.get("stocks") or result.get("expected_stocks") or 25)
    lines = [
        "*[KR 관심종목 리포트]*",
        _kr_watchlist_intro_line(),
        "",
        "오늘은 관심 섹터 5개와 관심종목 25개를 기준으로",
        "관찰 우선 종목과 대기 종목을 정리했습니다.",
        "",
    ]
    if briefing_url:
        lines.extend(["🔗 *리포트 보기*", briefing_url, ""])
    lines.extend(
        [
            "*상태 확인*",
            "✅ 리포트 생성 완료",
            f"✅ 관심 섹터: {sectors}개",
            f"✅ 관심 종목: {stocks}개",
            "✅ 라벨: 안 사면 후회함 / 지금 사기엔 좀...",
        ]
    )
    return "\n".join(lines)


def log_thread_send_result(
    *,
    slot: str,
    channel: str,
    main_message_ts: str | None,
    thread_count: int,
    sector_thread_status: list[dict[str, Any]],
    send_rows: list[dict[str, Any]],
    main_text: str,
    ok: bool,
    errors: list[str] | None = None,
) -> None:
    """슬랙 쓰레드 발송 메타 + 종목별 로그."""
    from agents.kr_intraday_slack.send_log import append_log_record

    append_log_record(
        {
            "slot": slot,
            "ticker": "",
            "name": "",
            "status": "thread_bundle",
            "sent": ok,
            "main_message_ts": main_message_ts,
            "thread_count": thread_count,
            "sector_thread_status": sector_thread_status,
            "main_message_preview": (main_text or "")[:200],
            "skip_reason": None if ok else "; ".join(errors or []),
        }
    )
    for row in send_rows:
        append_log_record(
            {
                "slot": slot,
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "status": row.get("ai_decision") or row.get("status"),
                "current_price": row.get("current_price_fmt"),
                "entry_range": row.get("entry_range"),
                "sent": ok,
                "main_message_ts": main_message_ts,
                "thread_count": thread_count,
                "sector_thread_status": sector_thread_status,
                "slack_stock_block": row.get("slack_stock_block"),
                "skip_reason": None if ok else "; ".join(errors or []),
                "grok_context": row.get("grok_context"),
                "gemini_polish": row.get("gemini_polish"),
                "slack_message_draft": row.get("slack_message_draft"),
            }
        )


def send_slack_threaded_messages(
    main_text: str,
    thread_messages: list[str],
    *,
    channel: str,
    retries: int = 1,
) -> dict[str, Any]:
    """메인 1건 + 쓰레드 N건 순차 발송."""
    if not channel:
        return {"ok": False, "error": "Slack channel missing", "skipped": True}

    posted_main = post_message(main_text, channel, retries=retries)
    if not posted_main.get("ok"):
        return {
            "ok": False,
            "main_message_ts": None,
            "thread_count": len(thread_messages),
            "thread_posted": 0,
            "sector_thread_status": [],
            "errors": [str(posted_main.get("error", "main_post_failed"))],
        }

    main_ts = posted_main.get("ts")
    sector_thread_status: list[dict[str, Any]] = []
    thread_errors: list[str] = []
    posted_threads = 0

    for idx, text in enumerate(thread_messages):
        if not text or not str(text).strip():
            sector_thread_status.append(
                {"index": idx, "ok": False, "error": "empty_thread"}
            )
            continue
        posted = post_message(text, channel, thread_ts=main_ts, retries=retries)
        entry: dict[str, Any] = {
            "index": idx,
            "ok": bool(posted.get("ok")),
            "ts": posted.get("ts"),
        }
        if not posted.get("ok"):
            entry["error"] = str(posted.get("error", "unknown"))
            thread_errors.append(entry["error"])
        else:
            posted_threads += 1
        sector_thread_status.append(entry)

    ok = bool(posted_main.get("ok")) and (
        not thread_messages or posted_threads == len(thread_messages)
    )
    return {
        "ok": ok,
        "main_message_ts": main_ts,
        "thread_count": len(thread_messages),
        "thread_posted": posted_threads,
        "sector_thread_status": sector_thread_status,
        "errors": thread_errors,
        "channel": channel,
        "posts": 1 + posted_threads,
    }


def send_kr_intraday_slack(
    result: Any,
    *,
    report_type: str = "kr_during",
) -> dict[str, Any]:
    """
    장중 관심종목 스캔 — 메인 요약 + 섹터별 쓰레드 발송.
    result: agents.kr_intraday_slack.IntradayScanResult
    """
    main_text = str(getattr(result, "main_message", "") or "").strip()
    thread_payload = list(getattr(result, "thread_messages", None) or [])
    send_rows = list(getattr(result, "send_rows", None) or [])
    slot = str(getattr(result, "slot", ""))

    if not main_text:
        legacy = list(getattr(result, "messages", None) or [])
        if legacy:
            main_text = legacy[0]
            thread_payload = [{"text": t} for t in legacy[1:]]

    if not main_text:
        return {"ok": True, "skipped": True, "reason": "no_main_message", "count": 0}

    thread_texts = [
        str(th.get("text", th) if isinstance(th, dict) else th).strip()
        for th in thread_payload
    ]
    thread_texts = [t for t in thread_texts if t]

    channel = resolve_slack_channel(report_type) or config.SLACK_CHANNEL_KR or os.getenv(
        "SLACK_CHANNEL_KR", ""
    )
    posted = send_slack_threaded_messages(
        main_text, thread_texts, channel=channel or "", retries=1
    )
    ok = bool(posted.get("ok"))
    errors = list(posted.get("errors") or [])
    if not ok and not errors:
        errors.append("thread_send_failed")

    raw_status = list(posted.get("sector_thread_status") or [])
    sector_status: list[dict[str, Any]] = []
    for i, th in enumerate(thread_payload):
        base = raw_status[i] if i < len(raw_status) else {"index": i, "ok": False}
        meta = dict(base)
        if isinstance(th, dict):
            meta["sector"] = th.get("sector", "")
            meta["stock_count"] = th.get("stock_count", 0)
        sector_status.append(meta)

    log_thread_send_result(
        slot=slot,
        channel=channel or "",
        main_message_ts=posted.get("main_message_ts"),
        thread_count=int(posted.get("thread_count") or len(thread_texts)),
        sector_thread_status=sector_status,
        send_rows=send_rows,
        main_text=main_text,
        ok=ok,
        errors=errors,
    )

    return {
        "ok": ok,
        "channel": channel,
        "count": len(send_rows) if ok else 0,
        "posts": posted.get("posts", 0),
        "main_message_ts": posted.get("main_message_ts"),
        "thread_count": posted.get("thread_count"),
        "thread_posted": posted.get("thread_posted"),
        "sector_thread_status": sector_status,
        "errors": errors,
    }


def send_kr_watchlist_report_slack(
    result: dict[str, Any],
    briefing_url: str = "",
    *,
    report_type: str = "kr_during",
) -> dict[str, Any]:
    """
    KR 관심종목 리포트 Slack 발송 — send_market_report와 동일 패턴
    (chat.postMessage + 브리핑 보기 버튼).
    """
    if not config.legacy_report_slack_enabled():
        return _legacy_slack_skipped(report_type)

    channel = resolve_slack_channel(report_type) or config.SLACK_CHANNEL_KR or os.getenv("SLACK_CHANNEL_KR", "")
    text = build_kr_watchlist_report_slack_text(result, briefing_url)
    blocks = _briefing_blocks(text, briefing_url)
    fallback = text if not briefing_url else f"{text}\n\n브리핑: {briefing_url}"
    posted = post_message(fallback, channel, blocks=blocks, retries=1)
    return {
        "ok": bool(posted.get("ok")),
        "channel": channel,
        "briefing_url": briefing_url or None,
        "errors": [] if posted.get("ok") else [str(posted.get("error", "unknown"))],
        "ts": posted.get("ts"),
    }
