"""Auto-correct: wrong numbers are replaced with source values and re-verified."""

from checker.autofix import autofix
from checker.facts import Fact
from checker.metrics import load_csv
from checker.models import Claim, Sentence, Summary
from checker.pipeline import correct, run
from checker.report import report_html, summary_html
from checker.sample_data import BRAND, OUT
from checker.verifier import verify

FACTS = {
    "c.cpa.current": Fact("c.cpa.current", "CPA", 35.34, "aed", "AED 35.34"),
    "c.ctr.wow_pct": Fact("c.ctr.wow_pct", "CTR WoW", -35.62, "pct_change", "-35.6%"),
    "c.roas.current": Fact("c.roas.current", "ROAS", 8.05, "x", "8.05x"),
    "t.spend.current": Fact("t.spend.current", "Spend", 30628.19, "aed", "AED 30,628"),
}


def one(text, *claims):
    s = Sentence(text=text, claims=[Claim(number_text=n, fact_id=f) for n, f in claims])
    return Summary(headline=s, what_changed=[], underperforming=[], recommendations=[])


def fix(summary):
    fixed, fixes = autofix(summary, verify(summary, FACTS), FACTS)
    return fixed.headline.text, fixes, verify(fixed, FACTS)


def test_wrong_value_is_replaced_keeping_the_currency_prefix():
    text, fixes, v = fix(one("CPA is now AED 47.71.", ("AED 47.71", "c.cpa.current")))
    assert text == "CPA is now AED 35.34."
    assert [(f.kind, f.before, f.after) for f in fixes] == [("value", "47.71", "35.34")]
    assert v.ready


def test_unsigned_change_stays_unsigned_and_signed_stays_signed():
    assert fix(one("CTR fell 41.0%.", ("41.0%", "c.ctr.wow_pct")))[0] == "CTR fell 35.6%."
    assert fix(one("CTR changed (-41.0%).", ("-41.0%", "c.ctr.wow_pct")))[0] == "CTR changed (-35.6%)."


def test_wrong_direction_word_is_swapped():
    text, fixes, v = fix(one("CTR rose 35.6% this week.", ("35.6%", "c.ctr.wow_pct")))
    assert text == "CTR fell 35.6% this week."
    assert fixes[0].kind == "direction" and v.ready


def test_several_fixes_in_one_sentence():
    text, _, v = fix(one("ROAS was 9.10x on AED 31,000.", ("9.10x", "c.roas.current"), ("AED 31,000", "t.spend.current")))
    assert text == "ROAS was 8.05x on AED 30,628."
    assert v.ready


def test_unsupported_number_is_left_for_a_human():
    text, fixes, v = fix(one("CPA is AED 35.34 across 3 campaigns.", ("AED 35.34", "c.cpa.current")))
    assert text == "CPA is AED 35.34 across 3 campaigns."
    assert [f.kind for f in fixes] == ["manual"]
    assert not v.ready


def test_trap_is_corrected_end_to_end():
    trapped = run(load_csv(OUT), BRAND, use_llm=False, trap=True)
    assert not trapped.verification.ready
    fixed = correct(trapped)
    assert fixed.verification.ready
    assert fixed.original_score == trapped.verification.score()
    assert [f.after for f in fixed.fixes] == [trapped.trap.original]
    html = summary_html(fixed)
    assert 'class="num corrected"' in html and "Auto-corrected" in html
    assert "auto-corrected from the source data" in report_html(fixed)
    assert trapped.verification.ready is False  # the original result is untouched
