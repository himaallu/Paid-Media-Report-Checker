"""Auto-correct: replace every wrong number with the value from the source data.

This is deterministic (no LLM call). For a MISMATCH the verifier already knows which
fact the number quotes, so the number is swapped for that fact's value, and a wrong
direction word ("rose" when it fell) is swapped for its opposite. UNSUPPORTED numbers
aren't linked to any metric, so they can't be fixed automatically and stay flagged.

The corrected summary is always checked again by the full verifier, never trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from checker.facts import Fact
from checker.models import Summary
from checker.verifier import DIRECTION_WINDOW, MISMATCH, UNSUPPORTED, Verification, extract_numbers

OPPOSITE = {
    "rose": "fell", "fell": "rose", "rise": "fall", "fall": "rise", "rising": "falling", "falling": "rising",
    "increase": "decrease", "decrease": "increase", "increased": "decreased", "decreased": "increased",
    "up": "down", "down": "up", "grew": "shrank", "shrank": "grew", "higher": "lower", "lower": "higher",
    "jumped": "dropped", "dropped": "jumped", "drop": "rise", "climbed": "fell", "gained": "lost", "lost": "gained",
    "declined": "rose", "decline": "rise", "slipped": "rose", "dipped": "rose", "spiked": "fell", "surged": "fell",
}


@dataclass(frozen=True)
class Fix:
    section: str
    index: int
    fact_id: str | None
    kind: str  # value | direction | manual
    before: str
    after: str


def _number_text(fact: Fact, signed: bool, has_currency_prefix: bool) -> str:
    """The fact's value written the way the sentence writes numbers."""
    text = fact.display
    if fact.unit == "pct_change" and not signed:
        text = text.lstrip("+-")  # "fell 35.6%" keeps its unsigned style
    if has_currency_prefix and text.startswith("AED "):
        text = text[len("AED ") :]  # "AED " is already in the sentence
    return text


def _swap_direction(text: str, number_start: int, previous_end: int) -> tuple[str, str, str] | None:
    """Swap the nearest direction word before the number. Returns (new_text, old_word, new_word)."""
    lo = max(previous_end, number_start - DIRECTION_WINDOW)
    words = list(re.finditer(r"[A-Za-z]+", text[lo:number_start]))
    for m in reversed(words):
        word = m.group(0)
        new = OPPOSITE.get(word.lower())
        if new:
            if word[0].isupper():
                new = new.capitalize()
            start, end = lo + m.start(), lo + m.end()
            return text[:start] + new + text[end:], word, new
    return None


def autofix(summary: Summary, verification: Verification, facts: dict[str, Fact]) -> tuple[Summary, list[Fix]]:
    fixed = summary.model_copy(deep=True)
    sentences = {(section, index): s for section, index, s in fixed.sentences()}
    fixes: list[Fix] = []

    for sc in verification.sentences:
        failing = [c for c in sc.checks if c.status != "verified"]
        if not failing:
            continue
        sentence = sentences[(sc.section, sc.index)]
        tokens = {t.start: t for t in extract_numbers(sentence.text)}
        starts = sorted(tokens)
        # Right to left, so earlier offsets stay valid after each replacement.
        for check in sorted(failing, key=lambda c: c.start, reverse=True):
            fact = facts.get(check.fact_id or "")
            if check.status == UNSUPPORTED or fact is None:
                fixes.append(Fix(sc.section, sc.index, check.fact_id, "manual", check.raw, ""))
                continue
            if check.status != MISMATCH:
                continue
            token = tokens[check.start]
            text = sentence.text
            if check.message.startswith("Says it"):
                prev_end = max((tokens[s].end for s in starts if s < check.start), default=0)
                swapped = _swap_direction(text, check.start, prev_end)
                if swapped is None:
                    fixes.append(Fix(sc.section, sc.index, check.fact_id, "manual", check.raw, ""))
                    continue
                sentence.text, old, new = swapped
                fixes.append(Fix(sc.section, sc.index, check.fact_id, "direction", old, new))
                continue
            new_number = _number_text(fact, token.signed, text[: token.start].endswith("AED "))
            sentence.text = text[: token.start] + new_number + text[token.end :]
            for claim in sentence.claims:
                if claim.fact_id == check.fact_id:
                    claim.number_text = fact.display
            fixes.append(Fix(sc.section, sc.index, check.fact_id, "value", check.raw, new_number))
    return fixed, fixes
