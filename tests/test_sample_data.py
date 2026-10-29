"""The demo dataset must keep its three patterns, and the committed CSV must match the generator."""

import pandas as pd

from checker.facts import build_signals
from checker.metrics import clean, compute, load_csv
from checker.sample_data import OUT, generate


def test_committed_csv_matches_generator():
    committed = load_csv(OUT)
    fresh = clean(generate())
    pd.testing.assert_frame_equal(committed.reset_index(drop=True), fresh.reset_index(drop=True), check_dtype=False)


def test_shape():
    df = generate()
    assert len(df) == 12 * 14
    assert set(df.platform) == {"Meta", "Google"}
    assert df.campaign.nunique() == 6


def test_demo_patterns_are_present():
    m = compute(load_csv(OUT))
    kinds = {(s.kind, s.entity) for s in build_signals(m)}
    assert ("cpa_spike", "Iced Spanish Latte Launch") in kinds
    assert ("ctr_drop", "Reels Brand Awareness") in kinds
    assert ("top_roas", "Search - Brand Terms") in kinds
