"""Tokens, cost and latency for every LLM call."""

from __future__ import annotations

from dataclasses import dataclass

# USD per 1M tokens on the paid tier (input, output incl. thinking), from
# https://ai.google.dev/gemini-api/docs/pricing (checked 29 Oct 2026). The free tier
# costs nothing; we show what the call would cost on the paid tier.
# Models not listed show "n/a".
PRICES_PER_M = {
    "gemini-3-flash-preview": (0.50, 3.00),
}


@dataclass
class LLMCall:
    model: str
    status: str  # ok | invalid_output | rate_limited | error | skipped
    latency_s: float
    input_tokens: int = 0
    output_tokens: int = 0  # includes thinking tokens, which are billed as output
    thinking_tokens: int = 0
    note: str = ""

    @property
    def cost_usd(self) -> float | None:
        price = PRICES_PER_M.get(self.model)
        if price is None:
            return None
        return (self.input_tokens * price[0] + self.output_tokens * price[1]) / 1_000_000


def totals(calls: list[LLMCall]) -> dict[str, float | int | None]:
    costs = [c.cost_usd for c in calls]
    return {
        "calls": len(calls),
        "input_tokens": sum(c.input_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "latency_s": round(sum(c.latency_s for c in calls), 2),
        "cost_usd": None if any(x is None for x in costs) else sum(x for x in costs if x is not None),
    }
