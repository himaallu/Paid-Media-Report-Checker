"""Hallucination trap: change one number after the summary is written.

It edits the sentence text and the claim's `number_text` together, keeping the
correct fact id, which is exactly what a real hallucination looks like: the right
metric with the wrong value. The verifier must flag it as a MISMATCH.
"""

from __future__ import annotations

from dataclasses import dataclass

from checker.facts import Fact
from checker.models import Summary
from checker.verifier import NumberToken, extract_numbers

# Prefer the numbers a client would act on.
PREFERRED_METRICS = (".cpa.current", ".roas.current", ".ctr.current", ".cpa.wow_pct", ".spend.current")
FACTOR = 1.35


@dataclass(frozen=True)
class TrapInfo:
    section: str
    index: int
    fact_id: str
    original: str
    injected: str


def _bump(text: str, token: NumberToken) -> str:
    digits = text[token.num_start : token.num_end]
    value = float(digits.replace(",", "")) * token.multiplier
    new = value * FACTOR if value else 5.0
    new /= token.multiplier
    if "," in digits or (token.decimals == 0 and new >= 1000):
        out = f"{new:,.{token.decimals}f}"
    else:
        out = f"{new:.{token.decimals}f}"
    return text[: token.num_start] + out + text[token.num_end :]


def inject(summary: Summary, facts: dict[str, Fact]) -> tuple[Summary, TrapInfo | None]:
    s = summary.model_copy(deep=True)
    candidates = []
    for section, index, sentence in s.sentences():
        if section == "headline":
            continue
        for claim in sentence.claims:
            if claim.fact_id not in facts:
                continue
            rank = next((i for i, suf in enumerate(PREFERRED_METRICS) if claim.fact_id.endswith(suf)), len(PREFERRED_METRICS))
            candidates.append((not claim.fact_id.startswith("campaign."), rank, section, index, sentence, claim))
    candidates.sort(key=lambda c: (c[0], c[1]))  # campaign-level first, then by metric preference

    for _, _, section, index, sentence, claim in candidates:
        claim_token = extract_numbers(claim.number_text)[0]
        for token in extract_numbers(sentence.text):
            if abs(abs(token.value) - abs(claim_token.value)) < 1e-9 and token.decimals == claim_token.decimals:
                new_text = _bump(sentence.text, token)
                original = sentence.text[token.start : token.end].strip()
                injected = new_text[token.start : token.end + (len(new_text) - len(sentence.text))].strip()
                sentence.text = new_text
                claim.number_text = _bump(claim.number_text, claim_token)
                return s, TrapInfo(section, index, claim.fact_id, original, injected)
    return s, None
