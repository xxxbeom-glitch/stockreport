# -*- coding: utf-8
"""Write REPLAY result JSON to GITHUB_OUTPUT and GITHUB_STEP_SUMMARY (CI only)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_result(path: Path) -> dict:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    return json.loads(raw)


def _append_github_output(key: str, value: str) -> None:
    out_path = os.getenv("GITHUB_OUTPUT")
    if not out_path:
        return
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def _append_step_summary(lines: list[str]) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    p = Path(summary_path)
    existing = p.read_text(encoding="utf-8") if p.is_file() else ""
    p.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    result_path = Path(sys.argv[1] if len(sys.argv) > 1 else "replay_result.json")
    result = _load_result(result_path)
    if not result:
        print(f"No result at {result_path}", file=sys.stderr)
        return 0

    ok = "true" if result.get("ok") else "false"
    cid = str(result.get("campaign_id") or "")
    needs = "true" if result.get("needs_resume") else "false"

    _append_github_output("ok", ok)
    if cid:
        _append_github_output("campaign_id", cid)
    _append_github_output("needs_resume", needs)

    chunk_dates = result.get("chunk_processed_dates") or []
    lines = [
        "## REPLAY chunk result",
        f"- **campaign_id**: `{cid or '(missing)'}`",
        f"- **progress**: {result.get('progress_label', '')}",
        f"- **chunk dates**: {', '.join(chunk_dates) if chunk_dates else '(none)'}",
        f"- **days**: {result.get('days_completed')} / {result.get('days_total')}",
        f"- **needs_resume**: {result.get('needs_resume')}",
        f"- **next_trading_date**: {result.get('next_trading_date', '')}",
        f"- **status**: {result.get('competition_status', '')}",
        f"- **batch_status**: {result.get('batch_status', '')}",
        f"- **resume_reason**: {result.get('resume_reason', '')}",
        f"- **kis_requests_used**: {result.get('kis_requests_used', '')}",
        f"- **ok**: {result.get('ok')}",
        f"- **data_status**: {result.get('data_status', '')}",
    ]
    if result.get("error"):
        lines.append(f"- **error**: `{result.get('error')}`")
    if result.get("needs_resume") and cid:
        lines.extend(
            [
                "",
                "다음 주차 이어 실행:",
                f"- `resume_existing_campaign`: true",
                f"- `campaign_id`: `{cid}`",
                f"- `replay_type`: `{result.get('replay_type', 'month')}`",
            ]
        )
    _append_step_summary(lines)

    print(json.dumps({"ok": ok, "campaign_id": cid, "needs_resume": needs}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
