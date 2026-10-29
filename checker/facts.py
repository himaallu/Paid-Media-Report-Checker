"""Turn computed metrics into the flat fact list the writer may quote, plus
deterministic signals (what is worth talking about).

Fact ids look like `campaign.iced_spanish_latte_launch.cpa.current`,
`platform.meta.roas.wow_pct` or `total.spend.previous`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from checker.metrics import LABELS, MetricsResult

# Signal thresholds (week-over-week %, ROAS multiple).
CPA_SPIKE_PCT = 25.0
CTR_DROP_PCT = -15.0
ROAS_DROP_PCT = -20.0
STRONG_ROAS = 3.0


@dataclass(frozen=True)
class Fact:
    fact_id: str
    label: str
    value: float
    unit: str  # aed | count | pct | x | pct_change
    display: str


@dataclass(frozen=True)
class Signal:
    kind: str  # cpa_spike | ctr_drop | roas_drop | top_roas | below_breakeven
    entity: str
    note: str
    fact_ids: tuple[str, ...]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def entity_prefix(entity_type: str, entity: str) -> str:
    return "total" if entity_type == "total" else f"{entity_type}.{slug(entity)}"


def fact_id(entity_type: str, entity: str, metric: str, column: str) -> str:
    return f"{entity_prefix(entity_type, entity)}.{metric}.{column}"


def unit_of(metric: str) -> str:
    if metric in ("spend", "revenue", "cpc", "cpa"):
        return "aed"
    if metric in ("ctr", "cvr"):
        return "pct"
    if metric == "roas":
        return "x"
    return "count"


def fmt(value: float, unit: str, metric: str = "") -> str:
    if unit == "pct_change":
        return f"{value:+.1f}%"
    if unit == "aed":
        return f"AED {value:,.0f}" if metric in ("spend", "revenue") else f"AED {value:,.2f}"
    if unit == "pct":
        return f"{value:.2f}%"
    if unit == "x":
        return f"{value:.2f}x"
    return f"{value:,.0f}"


def build_facts(m: MetricsResult) -> dict[str, Fact]:
    facts: dict[str, Fact] = {}
    for row in m.table.itertuples():
        name = "all campaigns" if row.entity_type == "total" else row.entity
        for column in ("previous", "current", "wow_pct"):
            value = float(getattr(row, column))
            if math.isnan(value):
                continue  # undefined (e.g. CPA with zero conversions): not quotable
            unit = "pct_change" if column == "wow_pct" else unit_of(row.metric)
            when = {"previous": "previous week", "current": "this week", "wow_pct": "week-over-week change"}[column]
            fid = fact_id(row.entity_type, row.entity, row.metric, column)
            facts[fid] = Fact(fid, f"{name} {LABELS[row.metric]}, {when}", value, unit, fmt(value, unit, row.metric))
    return facts


def build_signals(m: MetricsResult) -> list[Signal]:
    t = m.table[m.table.entity_type == "campaign"]
    signals: list[Signal] = []

    def val(entity: str, metric: str, column: str) -> float:
        return m.value("campaign", entity, metric, column)

    def ids(entity: str, *pairs: tuple[str, str]) -> tuple[str, ...]:
        return tuple(fact_id("campaign", entity, metric, col) for metric, col in pairs)

    for entity in sorted(t.entity.unique()):
        cpa_wow, ctr_wow, roas_wow = val(entity, "cpa", "wow_pct"), val(entity, "ctr", "wow_pct"), val(entity, "roas", "wow_pct")
        if cpa_wow >= CPA_SPIKE_PCT:
            signals.append(Signal("cpa_spike", entity, "CPA rose sharply week over week",
                                  ids(entity, ("cpa", "previous"), ("cpa", "current"), ("cpa", "wow_pct"), ("cvr", "wow_pct"), ("cpc", "wow_pct"))))
        if ctr_wow <= CTR_DROP_PCT:
            signals.append(Signal("ctr_drop", entity, "CTR fell sharply (possible creative fatigue)",
                                  ids(entity, ("ctr", "previous"), ("ctr", "current"), ("ctr", "wow_pct"), ("impressions", "wow_pct"))))
        if roas_wow <= ROAS_DROP_PCT:
            signals.append(Signal("roas_drop", entity, "ROAS fell sharply week over week",
                                  ids(entity, ("roas", "previous"), ("roas", "current"), ("roas", "wow_pct"))))
        roas = val(entity, "roas", "current")
        if not math.isnan(roas) and roas < 1:
            signals.append(Signal("below_breakeven", entity, "Revenue is below spend (ROAS under 1x)",
                                  ids(entity, ("roas", "current"), ("spend", "current"), ("revenue", "current"))))

    roas_now = t[t.metric == "roas"].dropna(subset=["current"])
    if not roas_now.empty:
        best = roas_now.loc[roas_now.current.idxmax()]
        if best.current >= STRONG_ROAS:
            signals.append(Signal("top_roas", best.entity, "Highest ROAS of all campaigns",
                                  ids(best.entity, ("roas", "current"), ("roas", "wow_pct"), ("spend", "current"), ("revenue", "current"))))
    return signals


def overview_fact_ids() -> list[str]:
    return [fact_id("total", "", metric, col) for metric in ("spend", "revenue", "roas", "cpa", "conversions") for col in ("current", "wow_pct")]

