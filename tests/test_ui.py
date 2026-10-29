"""UI helpers: KPI tiles, WoW colouring, status and header HTML."""

from checker.metrics import compute, load_csv
from checker.pipeline import metrics_table, run
from checker.sample_data import BRAND, OUT
from checker.ui import BAD, GOOD, hero_html, kpis, roas_chart, status_html, style_metrics


def test_kpis_invert_cpa_and_neutral_spend():
    tiles = {label: (value, delta, colour) for label, value, delta, colour in kpis(compute(load_csv(OUT)))}
    assert tiles["CPA"][2] == "inverse"
    assert tiles["Spend"][2] == "off"
    assert tiles["ROAS"][0] == "2.48x"
    assert tiles["CPA"][1].endswith("WoW")


def test_wow_colours_are_direction_aware():
    table = metrics_table(compute(load_csv(OUT)))
    styles = style_metrics(table)._compute().ctx
    cols = list(table.columns)
    latte = list(table.index).index("Iced Spanish Latte Launch")
    cpa_up = styles[(latte, cols.index("CPA WoW"))]  # CPA +79.2% is bad
    roas_down = styles[(latte, cols.index("ROAS WoW"))]  # ROAS -43.8% is bad
    assert ("color", BAD) in cpa_up and ("color", BAD) in roas_down
    brand = list(table.index).index("Search - Brand Terms")
    assert ("color", GOOD) in styles[(brand, cols.index("CPA WoW"))]  # CPA -5.5% is good


def test_status_and_hero_reflect_verification():
    df = load_csv(OUT)
    ok = run(df, BRAND, use_llm=False)
    trapped = run(df, BRAND, use_llm=False, trap=True)
    assert "Ready to send" in status_html(ok, {}, False)
    assert "Not ready to send" in status_html(trapped, {}, False)
    assert "Blocked" in hero_html(trapped) and "Ready to send" in hero_html(ok)


def test_roas_chart_builds():
    assert roas_chart(compute(load_csv(OUT))).to_dict()["layer"]
