"""GitHub Actions / CLI 실행·Slack 타이밍 로그."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

KST = timezone(timedelta(hours=9))


@dataclass
class WorkflowRunLog:
    workflow_name: str
    scheduled_kst: str
    tag: str = ""
    started_at: float = field(default_factory=time.monotonic)
    started_kst: str = field(default_factory=lambda: datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"))
    slack_sent_kst: str | None = None
    counts: dict[str, Any] = field(default_factory=dict)

    def emit(self, msg: str, *, fn: Callable[[str], None] | None = None) -> None:
        prefix = f"[{self.tag or self.workflow_name}]" if self.tag else f"[{self.workflow_name}]"
        line = f"{prefix} {msg}"
        (fn or print)(line)

    def banner_start(self, *, fn: Callable[[str], None] | None = None) -> None:
        self.emit(f"예정 실행 시각(KST): {self.scheduled_kst}", fn=fn)
        self.emit(f"실제 시작 시각(KST): {self.started_kst}", fn=fn)

    def mark_slack_sent(self) -> None:
        self.slack_sent_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    def finish(self, *, ok: bool = True, fn: Callable[[str], None] | None = None) -> None:
        elapsed = time.monotonic() - self.started_at
        if self.slack_sent_kst:
            self.emit(f"실제 Slack 발송 시각(KST): {self.slack_sent_kst}", fn=fn)
            try:
                sched_dt = datetime.strptime(
                    f"{self.started_kst[:10]} {self.scheduled_kst}",
                    "%Y-%m-%d %H:%M",
                ).replace(tzinfo=KST)
                sent_dt = datetime.strptime(
                    self.slack_sent_kst, "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=KST)
                delay_sec = (sent_dt - sched_dt).total_seconds()
                self.emit(f"예정 대비 지연: {delay_sec:.0f}초", fn=fn)
            except ValueError:
                pass
        self.emit(f"전체 소요: {elapsed:.1f}초", fn=fn)
        for key, val in self.counts.items():
            self.emit(f"{key}: {val}", fn=fn)
        status = "정상 완료" if ok else "실패"
        self.emit(status, fn=fn)
