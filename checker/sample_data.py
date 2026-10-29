"""Synthetic two-week campaign export for a fictional Dubai coffee chain.

"Dune & Dallah Coffee" is made up. The data is seeded, so every run produces the
same CSV, with three patterns baked in for the demo:

- Iced Spanish Latte Launch (Meta): CPA spike in week 2 (conversion rate drops, CPC rises).
- Search - Brand Terms (Google): the strong ROAS winner.
- Reels Brand Awareness (Meta): falling CTR (creative fatigue).

Run `python -m checker.sample_data` to rewrite data/sample_campaigns.csv.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BRAND = "Dune & Dallah Coffee"
START = date(2026, 10, 12)  # Monday; two full weeks to Sunday 25 Oct
DAYS = 14
SEED = 7
OUT = Path(__file__).resolve().parent.parent / "data" / "sample_campaigns.csv"


@dataclass(frozen=True)
class AdSetSpec:
    platform: str
    campaign: str
    ad_set: str
    impressions: float  # per day, week 1
    ctr: float  # clicks / impressions
    cpc: float  # AED
    cvr: float  # conversions / clicks
    aov: float  # AED revenue per conversion
    # Week-2 multipliers, applied to the week-1 baseline.
    week2: dict[str, float] = field(default_factory=dict)


def _specs() -> list[AdSetSpec]:
    latte_w2 = {"cvr": 0.62, "cpc": 1.15}
    reels_w2 = {"ctr": 0.62, "impressions": 1.05}
    brand_w2 = {"cvr": 1.08}
    pmax_w2 = {"cvr": 1.06, "impressions": 1.04}
    return [
        AdSetSpec("Meta", "Iced Spanish Latte Launch", "Lookalike 1% UAE", 22000, 0.014, 1.10, 0.060, 32, latte_w2),
        AdSetSpec("Meta", "Iced Spanish Latte Launch", "Interest - Coffee Lovers", 18000, 0.012, 1.20, 0.055, 32, latte_w2),
        AdSetSpec("Meta", "Reels Brand Awareness", "Dubai 18-34", 60000, 0.009, 0.45, 0.012, 28, reels_w2),
        AdSetSpec("Meta", "Reels Brand Awareness", "Abu Dhabi 18-34", 40000, 0.0085, 0.42, 0.011, 28, reels_w2),
        AdSetSpec("Meta", "Loyalty App Installs", "Android", 18000, 0.011, 1.60, 0.090, 25),
        AdSetSpec("Meta", "Loyalty App Installs", "iOS", 14000, 0.012, 1.90, 0.085, 25),
        AdSetSpec("Google", "Search - Brand Terms", "Exact Match", 4000, 0.090, 0.90, 0.160, 45, brand_w2),
        AdSetSpec("Google", "Search - Brand Terms", "Phrase Match", 3000, 0.075, 0.95, 0.150, 45, brand_w2),
        AdSetSpec("Google", "Search - Coffee Near Me", "Dubai Marina", 9000, 0.045, 1.80, 0.070, 34),
        AdSetSpec("Google", "Search - Coffee Near Me", "Downtown Dubai", 8000, 0.042, 1.85, 0.068, 34),
        AdSetSpec("Google", "PMax - Beans & Gifts Online", "Coffee Beans", 30000, 0.012, 1.30, 0.035, 140, pmax_w2),
        AdSetSpec("Google", "PMax - Beans & Gifts Online", "Gift Boxes", 20000, 0.010, 1.40, 0.030, 180, pmax_w2),
    ]


def generate(seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for spec in _specs():
        for d in range(DAYS):
            day = START + timedelta(days=d)
            w2 = spec.week2 if d >= 7 else {}
            weekend = 1.10 if day.weekday() >= 5 else 1.0  # UAE weekend: Sat-Sun

            def noisy(base: float, key: str) -> float:
                return base * w2.get(key, 1.0) * rng.lognormal(0, 0.08)

            impressions = round(noisy(spec.impressions, "impressions") * weekend)
            clicks = round(impressions * noisy(spec.ctr, "ctr"))
            conversions = round(clicks * noisy(spec.cvr, "cvr"))
            spend = round(clicks * noisy(spec.cpc, "cpc"), 2)
            revenue = round(conversions * spec.aov * rng.lognormal(0, 0.05), 2)
            rows.append(
                {
                    "date": day.isoformat(),
                    "platform": spec.platform,
                    "campaign": spec.campaign,
                    "ad_set": spec.ad_set,
                    "spend": spend,
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": conversions,
                    "revenue": revenue,
                }
            )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df = generate()
    df.to_csv(OUT, index=False)
    print(f"wrote {len(df)} rows to {OUT}")
