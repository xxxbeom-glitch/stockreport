"""Simple token/cost logging for agent calls."""

from __future__ import annotations

from datetime import datetime
from typing import Any

KRW_PER_USD = 1500
PRICING: dict[str, dict[str, float]] = {
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 10.00},
    "gemini-3.1-flash-lite-preview": {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "grok-3": {"input": 1.25, "output": 2.50},
    "grok-4.3": {"input": 1.25, "output": 2.50},
    "deepseek-v4-flash": {"input": 0.27, "output": 1.10},
    "deepseek-v4-pro": {"input": 0.55, "output": 2.19},
}


class TokenLogger:
    """Collect token usage and print compact execution summary."""

    def __init__(self, report_type: str):
        self.report_type = report_type
        self.started_at = datetime.now()
        self.records: list[dict[str, Any]] = []

    def log(self, model: str, agent: str, input_tokens: int, output_tokens: int) -> None:
        price = PRICING.get(model, {"input": 0.0, "output": 0.0})
        in_cost = (input_tokens / 1_000_000) * float(price["input"])
        out_cost = (output_tokens / 1_000_000) * float(price["output"])
        cost_usd = in_cost + out_cost
        self.records.append(
            {
                "agent": agent,
                "model": model,
                "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens),
                "total_tokens": int(input_tokens) + int(output_tokens),
                "cost_usd": round(cost_usd, 6),
                "cost_krw": round(cost_usd * KRW_PER_USD, 2),
            }
        )

    def summary(self) -> dict[str, Any]:
        elapsed = int((datetime.now() - self.started_at).total_seconds())
        total_input = sum(int(r["input_tokens"]) for r in self.records)
        total_output = sum(int(r["output_tokens"]) for r in self.records)
        total_usd = round(sum(float(r["cost_usd"]) for r in self.records), 6)
        by_model: dict[str, dict[str, float]] = {}
        for r in self.records:
            m = str(r["model"])
            if m not in by_model:
                by_model[m] = {"input": 0.0, "output": 0.0, "cost_krw": 0.0}
            by_model[m]["input"] += float(r["input_tokens"])
            by_model[m]["output"] += float(r["output_tokens"])
            by_model[m]["cost_krw"] += float(r["cost_krw"])
        return {
            "report_type": self.report_type,
            "elapsed_sec": elapsed,
            "total_input": total_input,
            "total_output": total_output,
            "total_tokens": total_input + total_output,
            "total_usd": total_usd,
            "total_krw": round(total_usd * KRW_PER_USD, 2),
            "by_model": by_model,
            "detail": self.records,
        }

    def print_summary(self) -> dict[str, Any]:
        s = self.summary()
        print("\n" + "=" * 50)
        print(f"  Token Summary - {s['report_type']}")
        print("=" * 50)
        print(
            f"  Total tokens: {s['total_tokens']:,} "
            f"(in {s['total_input']:,} / out {s['total_output']:,})"
        )
        print(f"  Total cost: ${s['total_usd']} ~= {s['total_krw']:,.0f} KRW")
        for model, stat in s["by_model"].items():
            total = int(stat["input"] + stat["output"])
            print(f"  - {model}: {total:,} tokens, {stat['cost_krw']:,.0f} KRW")
        print("=" * 50 + "\n")
        return s

