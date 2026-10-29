"""CSV -> metrics -> facts -> summary -> (trap) -> verification."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from checker.facts import Fact, Signal, build_facts, build_signals, fmt, unit_of
from checker.llm_log import LLMCall
from checker.metrics import LABELS, MetricsResult, compute
from checker.models import Summary
from checker.offline_writer import write_offline
from checker.trap import TrapInfo, inject
from checker.verifier import Verification, verify
from checker.writer import WriterError, write_with_llm


@dataclass
class PipelineResult:
    brand: str
    metrics: MetricsResult
    facts: dict[str, Fact]
    signals: list[Signal]
    summary: Summary
    writer: str  # model name, or "offline template"
    verification: Verification
    calls: list[LLMCall] = field(default_factory=list)
    trap: TrapInfo | None = None
    notice: str = ""  # shown in the UI, e.g. why the offline writer was used


@dataclass
class Written:
    summary: Summary
    writer: str
    calls: list[LLMCall]
    notice: str = ""


def write(metrics: MetricsResult, facts: dict[str, Fact], signals: list[Signal], brand: str, use_llm: bool, client: object = None) -> Written:
    if not use_llm:
        return Written(write_offline(facts, signals, brand), "offline template", [])
    try:
        r = write_with_llm(facts, signals, metrics.period, brand, client=client)
        return Written(r.summary, r.model, r.calls)
    except WriterError as exc:
        notice = f"LLM unavailable ({exc}); used the offline template instead."
        return Written(write_offline(facts, signals, brand), "offline template", exc.calls, notice)


def run(
    df: pd.DataFrame,
    brand: str,
    use_llm: bool = True,
    trap: bool = False,
    client: object = None,
    written: Written | None = None,
) -> PipelineResult:
    """`written` reuses an earlier summary (e.g. toggling the trap without a new LLM call)."""
    metrics = compute(df)
    facts = build_facts(metrics)
    signals = build_signals(metrics)
    written = written or write(metrics, facts, signals, brand, use_llm, client)

    summary, trap_info = written.summary, None
    if trap:
        summary, trap_info = inject(summary, facts)
    return PipelineResult(
        brand, metrics, facts, signals, summary, written.writer, verify(summary, facts), written.calls, trap_info, written.notice
    )


TABLE_METRICS = ["spend", "revenue", "roas", "cpa", "ctr", "cpc", "cvr", "conversions"]
WOW_SHOWN = {"spend", "roas", "cpa", "ctr"}


def metrics_table(m: MetricsResult, entity_type: str = "campaign") -> pd.DataFrame:
    """Formatted strings for display: current week, with WoW % next to the key metrics."""
    wide = m.wide(entity_type)
    out = pd.DataFrame(index=wide.index)
    if "platform" in wide:
        out["Platform"] = wide["platform"]
    for metric in TABLE_METRICS:
        unit = unit_of(metric)
        out[LABELS[metric]] = [("–" if pd.isna(v) else fmt(v, unit, metric)) for v in wide[metric]]
        if metric in WOW_SHOWN:
            out[f"{LABELS[metric]} WoW"] = [("–" if pd.isna(v) else fmt(v, "pct_change")) for v in wide[f"{metric}_wow_pct"]]
    out.index.name = "Campaign" if entity_type == "campaign" else entity_type.title()
    return out
