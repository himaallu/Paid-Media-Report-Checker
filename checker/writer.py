"""LLM writer: computed facts in, structured summary out (Gemini).

The model only sees pre-formatted facts and must cite a fact id for every number
it writes. It never does arithmetic; the verifier checks that it didn't.

Models are tried in order (GEMINI_MODEL, then GEMINI_FALLBACK_MODELS). A 429 or
5xx moves to the next model; invalid output gets one corrective retry first.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from checker.facts import Fact, Signal
from checker.llm_log import LLMCall
from checker.metrics import Period
from checker.models import Summary
from checker.usage import UsageTracker

DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_FALLBACKS = "gemini-3.5-flash,gemini-3.1-flash-lite"
TIMEOUT_MS = 60_000

SYSTEM_PROMPT = """You write the weekly paid-media performance summary that an agency sends to its client's marketing manager.

You receive FACTS (pre-computed metrics, each with an id and a display value) and SIGNALS (what the analytics team flagged).

Rules for numbers. These are strict; a separate checker verifies every number you write.
1. Every number you write must be copied exactly from a fact's "display" value, e.g. "AED 35.34", "+79.2%", "8.05x".
2. For every number in a sentence, add a claim with that exact text as number_text and the fact's id as fact_id.
3. Never calculate anything: no sums, differences, averages, shares, multiples or re-rounding. If a number is not in FACTS, describe it in words.
4. Do not write any other digits: no dates, years, counts like "3 campaigns" (write "three"), ad set names or list numbering.
5. Direction words must match the sign: "rose/up" only for a positive change, "fell/down" only for a negative one.

Content:
- headline: one sentence on overall spend, revenue and ROAS.
- what_changed: two or three sentences on the biggest movements, by platform and campaign.
- underperforming: one to three sentences on the campaigns the SIGNALS flag, with the numbers that show it.
- recommendations: two or three concrete actions, each tied to a named campaign and a number that justifies it.
Tone: clear, calm and client-ready. Short sentences. No hype, no emojis, no markdown."""


class WriterError(RuntimeError):
    """Every model failed; the caller falls back to the offline writer."""

    def __init__(self, message: str, calls: list[LLMCall] | None = None):
        super().__init__(message)
        self.calls = calls or []


@dataclass
class WriterResult:
    summary: Summary
    model: str
    calls: list[LLMCall] = field(default_factory=list)


def build_payload(facts: dict[str, Fact], signals: list[Signal], period: Period, brand: str) -> str:
    return json.dumps(
        {
            "brand": brand,
            "period": period.label(),
            "signals": [{"kind": s.kind, "campaign": s.entity, "note": s.note, "fact_ids": list(s.fact_ids)} for s in signals],
            "facts": [{"id": f.fact_id, "label": f.label, "display": f.display} for f in facts.values()],
        },
        ensure_ascii=False,
    )


def model_chain() -> list[str]:
    first = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    rest = [m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACKS).split(",") if m.strip()]
    return [first] + [m for m in rest if m != first]


def make_client() -> Any:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise WriterError("GEMINI_API_KEY is not set")
    from google import genai
    from google.genai import types

    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def _usage(response: Any) -> tuple[int, int, int]:
    u = getattr(response, "usage_metadata", None)
    if u is None:
        return 0, 0, 0
    thinking = u.thoughts_token_count or 0
    return u.prompt_token_count or 0, (u.candidates_token_count or 0) + thinking, thinking


def _config(with_thinking: bool) -> Any:
    from google.genai import types

    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=Summary,
        temperature=0.2,
        thinking_config=types.ThinkingConfig(thinking_level="low") if with_thinking else None,
    )


def write_with_llm(
    facts: dict[str, Fact],
    signals: list[Signal],
    period: Period,
    brand: str,
    client: Any = None,
    models: list[str] | None = None,
    tracker: UsageTracker | None = None,
) -> WriterResult:
    from google.genai import errors

    client = client or make_client()
    calls: list[LLMCall] = []
    payload = build_payload(facts, signals, period, brand)

    for model in models or model_chain():
        if tracker is not None and tracker.remaining(model) == 0:
            calls.append(LLMCall(model, "skipped", 0.0, note="daily limit reached; not called"))
            continue
        contents: list[Any] = [payload]
        with_thinking = True
        for attempt in range(2):  # one corrective retry for invalid output
            started = time.perf_counter()
            try:
                response = client.models.generate_content(model=model, contents=contents, config=_config(with_thinking))
            except errors.ClientError as exc:
                elapsed = time.perf_counter() - started
                if exc.code == 400 and with_thinking and "think" in str(exc).lower():
                    calls.append(LLMCall(model, "error", elapsed, note="thinking level not supported; retrying without"))
                    with_thinking = False
                    continue
                if exc.code == 429 and tracker is not None and "perday" in str(exc).lower().replace(" ", "").replace("_", ""):
                    tracker.mark_exhausted(model)
                status = "rate_limited" if exc.code == 429 else "error"
                calls.append(LLMCall(model, status, elapsed, note=f"HTTP {exc.code}: {(exc.message or '')[:120]}"))
                break  # next model
            except errors.ServerError as exc:
                calls.append(LLMCall(model, "error", time.perf_counter() - started, note=f"HTTP {exc.code}"))
                break
            except Exception as exc:  # timeouts and network errors
                calls.append(LLMCall(model, "error", time.perf_counter() - started, note=type(exc).__name__))
                break

            elapsed = time.perf_counter() - started
            if tracker is not None:
                tracker.record(model)  # a request that got a reply counts against the daily quota
            tokens_in, tokens_out, thinking = _usage(response)
            try:
                summary = Summary.model_validate_json(response.text or "")
            except ValidationError as exc:
                calls.append(LLMCall(model, "invalid_output", elapsed, tokens_in, tokens_out, thinking, note=f"{exc.error_count()} validation error(s)"))
                if attempt == 0:
                    contents = [payload, "Your previous reply was not valid JSON for the schema. Reply again with only the JSON object."]
                continue
            calls.append(LLMCall(model, "ok", elapsed, tokens_in, tokens_out, thinking))
            return WriterResult(summary, model, calls)

    last = next((c.note for c in reversed(calls) if c.note), "")
    raise WriterError(f"no model returned a valid summary; last error: {last}" if last else "no model returned a valid summary", calls)
