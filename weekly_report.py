"""Weekly report orchestrator with graceful fallbacks."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from reports import generate_pdf
from utils.helpers import safe_json_parse
from utils.token_logger import TokenLogger


def _load_recent_reports(days: int = 7) -> list[dict[str, Any]]:
    try:
        module = __import__("firebase_client", fromlist=["get_recent"])
        fn = getattr(module, "get_recent", None)
        if callable(fn):
            data = fn(days=days)
            return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"[WARN] get_recent unavailable: {exc}")
    return []


def _build_weekly_with_optional_gemini(daily_reports: list[dict[str, Any]], logger: TokenLogger) -> dict[str, Any]:
    if not config.GEMINI_API_KEY:
        return {
            "report_type": "weekly",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "one_line_summary": "Gemini 미설정 환경: 주간 요약 최소본",
            "weekly_flow": {"money_in": [], "money_out": [], "reason": "Fallback"},
            "theme_survival": [],
            "agent_scoreboard": [],
            "stock_analysis": [],
            "next_week_calendar": [],
            "portfolio_checklist": ["현금 비중 점검", "손절 기준 점검"],
            "action_items": ["다음 주 핵심 섹터 2개만 추적"],
            "glossary": [],
            "meta": {"mode": "fallback-no-gemini", "daily_count": len(daily_reports)},
        }

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_PRO_MODEL)
        prompt = (
            "주간 리포트 JSON만 반환. fields: report_type,date,one_line_summary,"
            "weekly_flow,theme_survival,agent_scoreboard,stock_analysis,next_week_calendar,"
            "portfolio_checklist,action_items,glossary\n"
            f"DATA={json.dumps(daily_reports, ensure_ascii=False)[:5000]}"
        )
        response = model.generate_content(prompt)
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            logger.log(
                model=config.GEMINI_PRO_MODEL,
                agent="weekly_orchestrator",
                input_tokens=int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0),
            )
        parsed = safe_json_parse(getattr(response, "text", "") or "")
        if parsed:
            parsed.setdefault("report_type", "weekly")
            parsed.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
            parsed.setdefault("one_line_summary", "이번 주 시장 흐름 요약")
            return parsed
    except Exception as exc:
        print(f"[WARN] weekly gemini failed: {exc}")

    return {
        "report_type": "weekly",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "one_line_summary": "주간 생성 실패로 최소 결과 반환",
        "weekly_flow": {"money_in": [], "money_out": [], "reason": "Fallback"},
        "theme_survival": [],
        "agent_scoreboard": [],
        "stock_analysis": [],
        "next_week_calendar": [],
        "portfolio_checklist": [],
        "action_items": [],
        "glossary": [],
        "meta": {"mode": "fallback-on-error", "daily_count": len(daily_reports)},
    }


def _safe_save_and_send(report_data: dict[str, Any], saved_path: str, report_type: str) -> None:
    pdf_url = ""
    try:
        firebase = __import__("firebase_client", fromlist=["save_report"])
        save_fn = getattr(firebase, "save_report", None)
        if callable(save_fn):
            save_result = save_fn(
                payload={"report_data": report_data, "file_path": saved_path, "report_type": report_type}
            )
            if isinstance(save_result, dict):
                pdf_url = str(save_result.get("url", "") or "")
    except Exception as exc:
        print(f"[WARN] weekly save skipped: {exc}")

    try:
        slack = __import__("slack_sender", fromlist=["send_report"])
        send_fn = getattr(slack, "send_report", None)
        if callable(send_fn):
            send_fn(
                payload={
                    "message": f"{report_type} generated: {saved_path}",
                    "summary": report_data.get("one_line_summary", ""),
                    "report_type": report_type,
                    "pdf_url": pdf_url,
                }
            )
    except Exception as exc:
        print(f"[WARN] weekly send skipped: {exc}")


def run_weekly() -> dict[str, Any]:
    logger = TokenLogger("weekly")
    print(f"[INFO] Running report_type=weekly at {datetime.now().isoformat(timespec='seconds')}")

    daily_reports = _load_recent_reports(days=7)
    report_data = _build_weekly_with_optional_gemini(daily_reports, logger=logger)

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{datetime.now().strftime('%y%m%d')}_weekly.html"
    saved_path = generate_pdf(report_data, str(output_file))

    _safe_save_and_send(report_data, saved_path, "weekly")
    logger.print_summary()
    return {"report_type": "weekly", "saved_path": saved_path, "daily_count": len(daily_reports)}


if __name__ == "__main__":
    print(json.dumps(run_weekly(), ensure_ascii=False, indent=2))

