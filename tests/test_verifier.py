import pytest

from checker.facts import Fact, build_facts, build_signals
from checker.metrics import compute, load_csv
from checker.models import Claim, Sentence, Summary
from checker.offline_writer import write_offline
from checker.sample_data import BRAND, OUT
from checker.trap import inject
from checker.verifier import MISMATCH, UNSUPPORTED, VERIFIED, extract_numbers, verify

FACTS = {
    "c.cpa.current": Fact("c.cpa.current", "CPA", 41.27, "aed", "AED 41.27"),
    "c.cpa.wow_pct": Fact("c.cpa.wow_pct", "CPA WoW", 38.16, "pct_change", "+38.2%"),
    "c.ctr.wow_pct": Fact("c.ctr.wow_pct", "CTR WoW", -35.62, "pct_change", "-35.6%"),
    "c.roas.current": Fact("c.roas.current", "ROAS", 8.05, "x", "8.05x"),
    "t.spend.current": Fact("t.spend.current", "Spend", 30628.19, "aed", "AED 30,628"),
}


def one(text: str, *claims: tuple[str, str]) -> Summary:
    s = Sentence(text=text, claims=[Claim(number_text=n, fact_id=f) for n, f in claims])
    return Summary(headline=s, what_changed=[], underperforming=[], recommendations=[])


def statuses(summary: Summary) -> list[str]:
    return [c.status for c in verify(summary, FACTS).checks]


@pytest.mark.parametrize(
    "text, value, decimals, signed",
    [
        ("AED 1,234.56", 1234.56, 2, False),
        ("+79.2%", 79.2, 1, True),
        ("-36.8%", -36.8, 1, True),
        ("−5%", -5, 0, True),
        ("8.05x", 8.05, 2, False),
        ("12.4k impressions", 12400, 1, False),
        ("30,628", 30628, 0, False),
    ],
)
def test_extract_numbers(text, value, decimals, signed):
    (token,) = extract_numbers(text)
    assert token.value == pytest.approx(value)
    assert (token.decimals, token.signed) == (decimals, signed)


def test_extract_ignores_words_and_finds_every_number():
    assert [t.value for t in extract_numbers("CPA rose from AED 19.73 to AED 35.34 (+79.2%).")] == [19.73, 35.34, 79.2]


def test_correct_numbers_are_verified():
    s = one("CPA rose 38.2% to AED 41.27 while ROAS hit 8.05x.",
            ("38.2%", "c.cpa.wow_pct"), ("AED 41.27", "c.cpa.current"), ("8.05x", "c.roas.current"))
    assert statuses(s) == [VERIFIED] * 3
    assert verify(s, FACTS).ready


@pytest.mark.parametrize(
    "written, expected",
    [
        ("38.2%", VERIFIED),  # 38.16 rounds to 38.2
        ("38%", VERIFIED),  # 38.16 rounds to 38
        ("38.3%", MISMATCH),
        ("39%", MISMATCH),
    ],
)
def test_rounding_tolerance_follows_written_precision(written, expected):
    assert statuses(one(f"CPA rose {written}.", (written, "c.cpa.wow_pct"))) == [expected]


def test_rounded_currency_and_thousands():
    assert statuses(one("CPA was AED 41.", ("AED 41", "c.cpa.current"))) == [VERIFIED]
    assert statuses(one("CPA was AED 42.", ("AED 42", "c.cpa.current"))) == [MISMATCH]
    assert statuses(one("Spend was AED 30.6k.", ("AED 30.6k", "t.spend.current"))) == [VERIFIED]


def test_wrong_value_is_a_mismatch_with_the_correct_value():
    v = verify(one("CPA is now AED 47.71.", ("AED 47.71", "c.cpa.current")), FACTS)
    (check,) = v.checks
    assert check.status == MISMATCH
    assert check.expected == "AED 41.27"
    assert "AED 41.27" in check.message
    assert not v.ready


def test_number_without_a_claim_is_unsupported():
    s = one("CPA is AED 41.27 across 3 campaigns.", ("AED 41.27", "c.cpa.current"))
    assert statuses(s) == [VERIFIED, UNSUPPORTED]


def test_unknown_fact_id_is_unsupported():
    v = verify(one("Margin was 22%.", ("22%", "c.margin.current")), FACTS)
    assert v.checks[0].status == UNSUPPORTED
    assert "unknown metric" in v.checks[0].message


def test_claim_list_is_not_trusted_over_the_text():
    # The claim says 41.27 but the client-facing text says 47.71: the text is what counts.
    s = one("CPA is AED 47.71.", ("AED 41.27", "c.cpa.current"))
    assert statuses(s) == [UNSUPPORTED]


def test_direction_word_must_match_the_sign():
    assert statuses(one("CTR fell 35.6%.", ("35.6%", "c.ctr.wow_pct"))) == [VERIFIED]
    v = verify(one("CTR rose 35.6%.", ("35.6%", "c.ctr.wow_pct")), FACTS)
    assert v.checks[0].status == MISMATCH
    assert "fell" in v.checks[0].message


def test_explicit_sign_must_match():
    assert statuses(one("CPA changed (+38.2%).", ("+38.2%", "c.cpa.wow_pct"))) == [VERIFIED]
    assert statuses(one("CPA changed (-38.2%).", ("-38.2%", "c.cpa.wow_pct"))) == [MISMATCH]


def test_summary_with_no_numbers_is_not_ready():
    assert not verify(one("Performance was fine."), FACTS).ready


@pytest.fixture(scope="module")
def sample():
    m = compute(load_csv(OUT))
    facts = build_facts(m)
    return facts, write_offline(facts, build_signals(m), BRAND)


def test_offline_summary_fully_verifies(sample):
    facts, summary = sample
    v = verify(summary, facts)
    assert v.total >= 20
    assert v.ready, [c for c in v.checks if c.status != VERIFIED]


def test_trap_is_caught(sample):
    facts, summary = sample
    trapped, info = inject(summary, facts)
    assert info is not None and info.original != info.injected
    v = verify(trapped, facts)
    failed = [c for c in v.checks if c.status != VERIFIED]
    assert len(failed) == 1
    assert failed[0].status == MISMATCH
    assert failed[0].fact_id == info.fact_id
    assert failed[0].expected == facts[info.fact_id].display
    assert not v.ready
    # The original summary is untouched.
    assert verify(summary, facts).ready
