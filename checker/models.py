"""Structured summary the writer returns (LLM or offline template)."""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel, Field

SECTIONS = {
    "what_changed": "What changed",
    "underperforming": "What's underperforming",
    "recommendations": "Recommendations",
}


class Claim(BaseModel):
    number_text: str = Field(description="The number exactly as written in the sentence, e.g. 'AED 35.34' or '+79.2%'.")
    fact_id: str = Field(description="The id of the fact this number quotes.")


class Sentence(BaseModel):
    text: str
    claims: list[Claim] = Field(default_factory=list)


class Summary(BaseModel):
    headline: Sentence
    what_changed: list[Sentence]
    underperforming: list[Sentence]
    recommendations: list[Sentence]

    def sentences(self) -> Iterator[tuple[str, int, Sentence]]:
        yield "headline", 0, self.headline
        for section in SECTIONS:
            for i, s in enumerate(getattr(self, section)):
                yield section, i, s
