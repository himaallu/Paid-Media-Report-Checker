"""Deterministic metric calculations. This is the only place numbers are computed.

The latest 7 days in the export are the "current" week and the 7 days before them
the "previous" week. Ratios are computed from summed totals (never averaged per
row), and a ratio with a zero denominator is NaN, not 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import IO

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["date", "platform", "campaign", "ad_set", "spend", "impressions", "clicks", "conversions", "revenue"]
BASE = ["spend", "impressions", "clicks", "conversions", "revenue"]
RATIOS = ["ctr", "cpc", "cpa", "roas", "cvr"]
METRICS = BASE + RATIOS

# Display order and labels used everywhere (facts, tables, report).
LABELS = {
    "spend": "Spend",
    "impressions": "Impressions",
    "clicks": "Clicks",
    "conversions": "Conversions",
    "revenue": "Revenue",
    "ctr": "CTR",
    "cpc": "CPC",
    "cpa": "CPA",
    "roas": "ROAS",
    "cvr": "Conversion rate",
}


class DataError(ValueError):
    """The export can't be used (missing columns, bad values, not two weeks)."""


@dataclass(frozen=True)
class Period:
    previous_start: date
    previous_end: date
    current_start: date
    current_end: date

    def label(self) -> str:
        fmt = "%d %b %Y"
        return (
            f"{self.current_start.strftime('%d %b')} – {self.current_end.strftime(fmt)} "
            f"vs {self.previous_start.strftime('%d %b')} – {self.previous_end.strftime(fmt)}"
        )


@dataclass(frozen=True)
class MetricsResult:
    period: Period
    # Long format: entity_type (total|platform|campaign), entity, platform, metric,
    # previous, current, wow_pct.
    table: pd.DataFrame

    def value(self, entity_type: str, entity: str, metric: str, column: str) -> float:
        t = self.table
        row = t[(t.entity_type == entity_type) & (t.entity == entity) & (t.metric == metric)]
        if row.empty:
            raise KeyError((entity_type, entity, metric))
        return float(row.iloc[0][column])

    def wide(self, entity_type: str) -> pd.DataFrame:
        """One row per entity with current values and WoW % per metric (for display)."""
        t = self.table[self.table.entity_type == entity_type]
        cur = t.pivot(index="entity", columns="metric", values="current")[METRICS]
        wow = t.pivot(index="entity", columns="metric", values="wow_pct")[METRICS].add_suffix("_wow_pct")
        out = cur.join(wow)
        if entity_type == "campaign":
            platforms = t.drop_duplicates("entity").set_index("entity")["platform"]
            out.insert(0, "platform", platforms)
        return out


def load_csv(source: str | IO[bytes] | IO[str]) -> pd.DataFrame:
    try:
        df = pd.read_csv(source)
    except Exception as exc:  # pandas raises several types for unreadable files
        raise DataError(f"Could not read the CSV: {exc}") from exc
    return clean(df)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataError(f"Missing column(s): {', '.join(missing)}")
    df = df[REQUIRED_COLUMNS]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        raise DataError(f"{int(df['date'].isna().sum())} row(s) have an unreadable date")
    for col in BASE:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            raise DataError(f"Column '{col}' has non-numeric or empty values")
        if (df[col] < 0).any():
            raise DataError(f"Column '{col}' has negative values")
    for col in ["platform", "campaign", "ad_set"]:
        df[col] = df[col].astype(str).str.strip()
    return df


def split_weeks(df: pd.DataFrame) -> tuple[pd.DataFrame, Period]:
    end = df["date"].max().date()
    period = Period(
        previous_start=end - timedelta(days=13),
        previous_end=end - timedelta(days=7),
        current_start=end - timedelta(days=6),
        current_end=end,
    )
    d = df["date"].dt.date
    out = df.copy()
    out["week"] = np.where(d >= period.current_start, "current", np.where(d >= period.previous_start, "previous", None))
    out = out[out["week"].notna()]
    if not (out["week"] == "previous").any():
        raise DataError("The export needs two weeks of data: nothing found for the previous week")
    return out, period


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    return num.div(den.where(den != 0))


def add_ratios(sums: pd.DataFrame) -> pd.DataFrame:
    s = sums.copy()
    s["ctr"] = _safe_div(s["clicks"], s["impressions"]) * 100
    s["cpc"] = _safe_div(s["spend"], s["clicks"])
    s["cpa"] = _safe_div(s["spend"], s["conversions"])
    s["roas"] = _safe_div(s["revenue"], s["spend"])
    s["cvr"] = _safe_div(s["conversions"], s["clicks"]) * 100
    return s


def wow_pct(previous: float, current: float) -> float:
    if previous == 0 or np.isnan(previous) or np.isnan(current):
        return float("nan")
    return (current - previous) / previous * 100


def compute(df: pd.DataFrame) -> MetricsResult:
    weeks, period = split_weeks(df)
    rows = []
    groupings = [("total", None), ("platform", "platform"), ("campaign", "campaign")]
    for entity_type, key in groupings:
        keys = ["week"] if key is None else [key, "week"]
        sums = add_ratios(weeks.groupby(keys)[BASE].sum())
        entities = ["All campaigns"] if key is None else sorted(weeks[key].unique())
        for entity in entities:
            platform = None
            if entity_type == "campaign":
                platform = weeks.loc[weeks.campaign == entity, "platform"].iloc[0]
            for metric in METRICS:

                def get(week: str, entity: str = entity, metric: str = metric) -> float:
                    idx = week if key is None else (entity, week)
                    return float(sums[metric].get(idx, np.nan)) if idx in sums.index else float("nan")

                prev, cur = get("previous"), get("current")
                if metric in BASE:  # a missing week means nothing happened
                    prev, cur = np.nan_to_num(prev), np.nan_to_num(cur)
                rows.append(
                    {
                        "entity_type": entity_type,
                        "entity": entity,
                        "platform": platform,
                        "metric": metric,
                        "previous": prev,
                        "current": cur,
                        "wow_pct": wow_pct(prev, cur),
                    }
                )
    return MetricsResult(period=period, table=pd.DataFrame(rows))
