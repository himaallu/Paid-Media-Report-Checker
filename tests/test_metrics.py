"""Metric calculations against hand-worked numbers.

Previous week = 1-7 Oct, current week = 8-14 Oct (the export ends 14 Oct).

Campaign A (Meta)
  previous: spend 100, impressions 10,000, clicks 200, conversions 10, revenue 400
  current:  two rows summed -> spend 200, impressions 15,000, clicks 200, conversions 10, revenue 500
  CTR 2.00% -> 1.3333%   CPC 0.50 -> 1.00   CPA 10 -> 20   ROAS 4.0 -> 2.5   CVR 5% -> 5%
Campaign B (Google)
  previous: spend 50, impressions 1,000, clicks 50, conversions 0, revenue 0  (CPA undefined)
  current:  spend 60, impressions 1,200, clicks 40, conversions 2, revenue 240 (CPA 30, ROAS 4.0)
Total: spend 150 -> 260, revenue 400 -> 740, ROAS 2.6667 -> 2.8462 (+6.73%)
"""

import math

import pandas as pd
import pytest

from checker.metrics import DataError, clean, compute, wow_pct

ROWS = [
    # date, platform, campaign, ad_set, spend, impressions, clicks, conversions, revenue
    ("2026-09-20", "Meta", "A", "x", 999, 999, 99, 9, 999),  # older than two weeks: ignored
    ("2026-10-03", "Meta", "A", "x", 100, 10000, 200, 10, 400),
    ("2026-10-10", "Meta", "A", "x", 150, 12000, 180, 5, 300),
    ("2026-10-12", "Meta", "A", "y", 50, 3000, 20, 5, 200),
    ("2026-10-05", "Google", "B", "z", 50, 1000, 50, 0, 0),
    ("2026-10-14", "Google", "B", "z", 60, 1200, 40, 2, 240),
]
COLUMNS = ["date", "platform", "campaign", "ad_set", "spend", "impressions", "clicks", "conversions", "revenue"]


@pytest.fixture
def result():
    return compute(clean(pd.DataFrame(ROWS, columns=COLUMNS)))


def test_period_is_last_seven_days_vs_the_seven_before(result):
    p = result.period
    assert (str(p.previous_start), str(p.previous_end)) == ("2026-10-01", "2026-10-07")
    assert (str(p.current_start), str(p.current_end)) == ("2026-10-08", "2026-10-14")


@pytest.mark.parametrize(
    "metric, previous, current",
    [
        ("spend", 100, 200),
        ("impressions", 10000, 15000),
        ("ctr", 2.0, 200 / 15000 * 100),
        ("cpc", 0.5, 1.0),
        ("cpa", 10, 20),
        ("roas", 4.0, 2.5),
        ("cvr", 5.0, 5.0),
    ],
)
def test_campaign_metrics_use_summed_totals(result, metric, previous, current):
    assert result.value("campaign", "A", metric, "previous") == pytest.approx(previous)
    assert result.value("campaign", "A", metric, "current") == pytest.approx(current)


def test_week_over_week(result):
    assert result.value("campaign", "A", "spend", "wow_pct") == pytest.approx(100.0)
    assert result.value("campaign", "A", "cpa", "wow_pct") == pytest.approx(100.0)
    assert result.value("campaign", "A", "roas", "wow_pct") == pytest.approx(-37.5)
    assert result.value("campaign", "A", "ctr", "wow_pct") == pytest.approx(-33.3333, abs=1e-3)
    assert result.value("campaign", "A", "cvr", "wow_pct") == pytest.approx(0.0)


def test_zero_denominators_are_undefined_not_zero(result):
    assert math.isnan(result.value("campaign", "B", "cpa", "previous"))
    assert result.value("campaign", "B", "cpa", "current") == pytest.approx(30)
    assert math.isnan(result.value("campaign", "B", "cpa", "wow_pct"))
    assert math.isnan(result.value("campaign", "B", "roas", "wow_pct"))  # previous ROAS is 0


def test_platform_and_total(result):
    assert result.value("platform", "Google", "roas", "current") == pytest.approx(4.0)
    assert result.value("total", "All campaigns", "spend", "current") == pytest.approx(260)
    assert result.value("total", "All campaigns", "roas", "previous") == pytest.approx(400 / 150)
    assert result.value("total", "All campaigns", "roas", "current") == pytest.approx(740 / 260)
    assert result.value("total", "All campaigns", "roas", "wow_pct") == pytest.approx((740 / 260 - 400 / 150) / (400 / 150) * 100)


def test_wow_pct_edge_cases():
    assert wow_pct(50, 75) == pytest.approx(50.0)
    assert math.isnan(wow_pct(0, 10))
    assert math.isnan(wow_pct(float("nan"), 10))


def test_column_names_are_normalised():
    df = pd.DataFrame(ROWS, columns=[c.upper() + " " for c in COLUMNS])
    assert list(clean(df).columns) == COLUMNS


def test_missing_column_is_rejected():
    df = pd.DataFrame(ROWS, columns=COLUMNS).drop(columns="revenue")
    with pytest.raises(DataError, match="revenue"):
        clean(df)


def test_negative_values_are_rejected():
    rows = [list(r) for r in ROWS]
    rows[1][4] = -5
    with pytest.raises(DataError, match="negative"):
        clean(pd.DataFrame(rows, columns=COLUMNS))


def test_one_week_of_data_is_rejected():
    df = clean(pd.DataFrame([r for r in ROWS if r[0] >= "2026-10-08"], columns=COLUMNS))
    with pytest.raises(DataError, match="two weeks"):
        compute(df)
