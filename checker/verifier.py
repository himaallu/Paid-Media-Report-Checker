"""Check every number in a summary against the computed facts.

The sentence text is the source of truth, not the writer's claim list:

1. Every number in the text is extracted with a regex.
2. Each one is paired with a claim whose `number_text` states the same number.
   No claim -> UNSUPPORTED. A claim citing a fact id that doesn't exist -> UNSUPPORTED.
3. The number is compared with the computed value at the precision it was written:
   "38.2%" passes for 38.15..38.25, "AED 41" passes for 40.5..41.5.
   Week-over-week facts compare magnitudes unless the text gives an explicit sign,
   and a direction word just before the number ("rose", "fell", ...) must match the sign.
4. Anything not VERIFIED makes the report "not ready to send".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from checker.facts import Fact
from checker.models import Summary

VERIFIED, MISMATCH, UNSUPPORTED = "verified", "mismatch", "unsupported"

# Optional sign, digits (with thousands commas), decimals, k/M multiplier, then an optional unit.
NUMBER_RE = re.compile(
    r"(?<![\w.,])(?P<sign>[+\-−])?(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d+))?"
    r"(?P<mult>[kKmM](?![a-zA-Z]))?(?P<unit>\s?%|x(?![a-zA-Z])|×|\s?pp\b)?"
)
UP_WORDS = ("rose", "rise", "rising", "increase", "increased", "up", "grew", "growth", "jumped", "climbed", "higher", "gain", "gained", "spike", "spiked", "surged")
DOWN_WORDS = ("fell", "fall", "falling", "decrease", "decreased", "down", "dropped", "drop", "declined", "decline", "lower", "slipped", "shrank", "dipped", "lost")
DIRECTION_WINDOW = 40  # characters before the number to look for a direction word
SIGN_EPSILON = 0.05  # a change smaller than this (in %) has no meaningful direction


@dataclass(frozen=True)
class NumberToken:
    raw: str
    value: float  # signed, multiplier applied
    decimals: int
    multiplier: float
    signed: bool  # the text wrote an explicit + or -
    start: int
    end: int
    num_start: int  # span of the digits only, used by the trap
    num_end: int


def extract_numbers(text: str) -> list[NumberToken]:
    tokens = []
    for m in NUMBER_RE.finditer(text):
        digits = m.group("num").replace(",", "")
        dec = m.group("dec") or ""
        mult = {"k": 1e3, "m": 1e6}.get((m.group("mult") or "").lower(), 1.0)
        value = float(f"{digits}.{dec}" if dec else digits) * mult
        sign = m.group("sign")
        if sign in ("-", "−"):
            value = -value
        tokens.append(
            NumberToken(
                raw=m.group(0).strip(),
                value=value,
                decimals=len(dec),
                multiplier=mult,
                signed=sign is not None,
                start=m.start(),
                end=m.end(),
                num_start=m.start("num"),
                num_end=m.end("dec") if dec else m.end("num"),
            )
        )
    return tokens


def tolerance(token: NumberToken) -> float:
    return 0.5 * 10 ** (-token.decimals) * token.multiplier + 1e-9


def _direction(text: str, token: NumberToken, previous_end: int) -> int:
    """+1 / -1 if a direction word appears just before the number, else 0."""
    window = text[max(previous_end, token.start - DIRECTION_WINDOW) : token.start].lower()
    words = re.findall(r"[a-z]+", window)
    for word in reversed(words):  # the nearest word wins
        if word in UP_WORDS:
            return 1
        if word in DOWN_WORDS:
            return -1
    return 0


@dataclass
class NumberCheck:
    raw: str
    start: int
    end: int
    status: str
    fact_id: str | None = None
    expected: str | None = None  # the correct value, formatted
    message: str = ""


@dataclass
class SentenceCheck:
    section: str
    index: int
    text: str
    checks: list[NumberCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status == VERIFIED for c in self.checks)


@dataclass
class Verification:
    sentences: list[SentenceCheck]

    @property
    def checks(self) -> list[NumberCheck]:
        return [c for s in self.sentences for c in s.checks]

    @property
    def verified(self) -> int:
        return sum(c.status == VERIFIED for c in self.checks)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def ready(self) -> bool:
        return self.total > 0 and self.verified == self.total

    def score(self) -> str:
        return f"{self.verified}/{self.total} claims verified"


def check_number(token: NumberToken, fact: Fact, direction: int) -> tuple[str, str]:
    """Return (status, message) for one number against its fact."""
    actual = fact.value
    if fact.unit == "pct_change":
        if token.signed:
            if abs(token.value - actual) > tolerance(token):
                return MISMATCH, f"Source data: {fact.display}"
        elif abs(abs(token.value) - abs(actual)) > tolerance(token):
            return MISMATCH, f"Source data: {fact.display}"
        if direction and abs(actual) >= SIGN_EPSILON and (direction > 0) != (actual > 0):
            said, real = ("rose", "fell") if direction > 0 else ("fell", "rose")
            return MISMATCH, f"Says it {said}, but it {real}: {fact.display}"
        return VERIFIED, ""
    if abs(token.value - actual) > tolerance(token):
        return MISMATCH, f"Source data: {fact.display}"
    return VERIFIED, ""


def verify(summary: Summary, facts: dict[str, Fact]) -> Verification:
    results = []
    for section, index, sentence in summary.sentences():
        sc = SentenceCheck(section, index, sentence.text)
        # Pre-parse each claim's number so "AED 35.34" and "35.34" pair up.
        claims = []
        for claim in sentence.claims:
            parsed = extract_numbers(claim.number_text)
            claims.append((claim, parsed[0] if parsed else None))
        used: set[int] = set()
        previous_end = 0
        for token in extract_numbers(sentence.text):
            match = None
            for i, (claim, ct) in enumerate(claims):
                if i in used or ct is None:
                    continue
                if abs(ct.value - token.value) < 1e-9 and ct.decimals == token.decimals:
                    match = i
                    break
                if abs(abs(ct.value) - abs(token.value)) < 1e-9 and ct.decimals == token.decimals:
                    match = i  # same number, sign written differently
                    break
            check = NumberCheck(token.raw, token.start, token.end, UNSUPPORTED)
            if match is None:
                check.message = "This number isn't linked to any computed metric"
            else:
                used.add(match)
                claim = claims[match][0]
                check.fact_id = claim.fact_id
                fact = facts.get(claim.fact_id)
                if fact is None:
                    check.message = f"Cites an unknown metric '{claim.fact_id}'"
                else:
                    check.status, check.message = check_number(token, fact, _direction(sentence.text, token, previous_end))
                    check.expected = fact.display
            sc.checks.append(check)
            previous_end = token.end
        results.append(sc)
    return Verification(results)
