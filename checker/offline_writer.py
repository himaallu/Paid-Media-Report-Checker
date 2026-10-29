"""Template summary with no LLM: used when there's no API key or every model is
rate-limited, so the demo never dies. It quotes facts by id, so it always verifies."""

from __future__ import annotations

from checker.facts import Fact, Signal, entity_prefix
from checker.models import Claim, Sentence, Summary


class _Builder:
    def __init__(self, facts: dict[str, Fact]):
        self.facts = facts

    def sentence(self, template: str, **fids: str) -> Sentence | None:
        """`template` has {name} placeholders; each maps to a fact id. None if a fact is missing."""
        if any(fid not in self.facts for fid in fids.values()):
            return None
        values = {name: self.facts[fid].display for name, fid in fids.items()}
        claims = [Claim(number_text=values[name], fact_id=fid) for name, fid in fids.items()]
        return Sentence(text=template.format(**values), claims=claims)


def write_offline(facts: dict[str, Fact], signals: list[Signal], brand: str) -> Summary:
    b = _Builder(facts)

    def c(entity: str, metric: str, col: str) -> str:
        return f"{entity_prefix('campaign', entity)}.{metric}.{col}"

    def p(entity: str, metric: str, col: str) -> str:
        return f"{entity_prefix('platform', entity)}.{metric}.{col}"

    headline = b.sentence(
        "Total spend was {spend} ({spend_wow} week over week) and revenue {rev} ({rev_wow}), a blended ROAS of {roas}.",
        spend="total.spend.current", spend_wow="total.spend.wow_pct",
        rev="total.revenue.current", rev_wow="total.revenue.wow_pct", roas="total.roas.current",
    ) or Sentence(text=f"Weekly performance summary for {brand}.")

    what_changed: list[Sentence | None] = [
        b.sentence(
            "Google returned {g_roas} ROAS on {g_spend} of spend, against {m_roas} on {m_spend} for Meta.",
            g_roas=p("Google", "roas", "current"), g_spend=p("Google", "spend", "current"),
            m_roas=p("Meta", "roas", "current"), m_spend=p("Meta", "spend", "current"),
        ),
        b.sentence("Blended CPA was {cpa} ({cpa_wow}) across {conv} conversions.",
                   cpa="total.cpa.current", cpa_wow="total.cpa.wow_pct", conv="total.conversions.current"),
    ]
    underperforming: list[Sentence | None] = []
    recommendations: list[Sentence | None] = []
    mentioned_roas: set[str] = set()

    for s in signals:
        e = s.entity
        if s.kind == "top_roas":
            what_changed.append(b.sentence(f"{e} was the standout at {{roas}} ROAS ({{wow}}) from {{spend}} of spend.",
                                           roas=c(e, "roas", "current"), wow=c(e, "roas", "wow_pct"), spend=c(e, "spend", "current")))
            recommendations.append(b.sentence(f"Move budget toward {e}, which returns {{roas}} for every dirham spent.",
                                              roas=c(e, "roas", "current")))
        elif s.kind == "cpa_spike":
            underperforming.append(b.sentence(
                f"{e} CPA rose from {{prev}} to {{cur}} ({{wow}}), as conversion rate moved {{cvr}} and CPC {{cpc}}.",
                prev=c(e, "cpa", "previous"), cur=c(e, "cpa", "current"), wow=c(e, "cpa", "wow_pct"),
                cvr=c(e, "cvr", "wow_pct"), cpc=c(e, "cpc", "wow_pct")))
            recommendations.append(b.sentence(
                f"Review the landing page and pause the weakest ad set in {e} before adding budget; CPA is now {{cur}}.",
                cur=c(e, "cpa", "current")))
        elif s.kind == "ctr_drop":
            underperforming.append(b.sentence(
                f"{e} CTR fell from {{prev}} to {{cur}} ({{wow}}), a sign of creative fatigue.",
                prev=c(e, "ctr", "previous"), cur=c(e, "ctr", "current"), wow=c(e, "ctr", "wow_pct")))
            recommendations.append(b.sentence(f"Refresh the {e} creative this week; CTR is down to {{cur}}.",
                                              cur=c(e, "ctr", "current")))
        elif s.kind in ("roas_drop", "below_breakeven") and e not in mentioned_roas:
            mentioned_roas.add(e)
            underperforming.append(b.sentence(f"{e} returned {{roas}} ROAS on {{spend}} of spend, so it earned less than it cost."
                                              if s.kind == "below_breakeven" else
                                              f"{e} ROAS fell to {{roas}} on {{spend}} of spend.",
                                              roas=c(e, "roas", "current"), spend=c(e, "spend", "current")))

    def keep(items: list[Sentence | None], limit: int) -> list[Sentence]:
        return [s for s in items if s is not None][:limit]

    return Summary(
        headline=headline,
        what_changed=keep(what_changed, 3),
        underperforming=keep(underperforming, 3),
        recommendations=keep(recommendations, 3),
    )
