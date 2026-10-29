"""Daily Gemini call counter."""

from datetime import date

from google.genai import errors

from checker.facts import build_facts, build_signals
from checker.metrics import compute, load_csv
from checker.offline_writer import write_offline
from checker.sample_data import BRAND, OUT
from checker.usage import UsageTracker
from checker.writer import write_with_llm
from tests.test_writer import FakeClient, reply


def test_counts_per_model_and_remaining(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_LIMIT", "5")
    t = UsageTracker(tmp_path / "u.json", today=date(2026, 10, 29))
    t.record("a")
    t.record("a")
    t.record("b")
    assert (t.used("a"), t.remaining("a"), t.remaining("b"), t.remaining("c")) == (2, 3, 4, 5)


def test_count_resets_on_a_new_day(tmp_path):
    path = tmp_path / "u.json"
    UsageTracker(path, today=date(2026, 10, 29)).record("a")
    assert UsageTracker(path, today=date(2026, 10, 29)).used("a") == 1
    assert UsageTracker(path, today=date(2026, 10, 30)).used("a") == 0


def test_exhausted_model_has_nothing_left(tmp_path):
    t = UsageTracker(tmp_path / "u.json", today=date(2026, 10, 29))
    t.mark_exhausted("a")
    assert t.remaining("a") == 0


def test_corrupt_file_starts_fresh(tmp_path):
    path = tmp_path / "u.json"
    path.write_text("{not json")
    assert UsageTracker(path).used("a") == 0


def _sample():
    m = compute(load_csv(OUT))
    facts, signals = build_facts(m), build_signals(m)
    return m, facts, signals, write_offline(facts, signals, BRAND).model_dump_json()


def test_writer_counts_each_request_including_the_retry(tmp_path):
    m, facts, signals, good = _sample()
    t = UsageTracker(tmp_path / "u.json")
    write_with_llm(facts, signals, m.period, BRAND, client=FakeClient([reply("bad"), reply(good)]), models=["a"], tracker=t)
    assert t.used("a") == 2


def test_daily_quota_429_marks_model_exhausted_and_it_is_skipped_next_time(tmp_path):
    m, facts, signals, good = _sample()
    t = UsageTracker(tmp_path / "u.json")
    quota = errors.ClientError(429, {"error": {"message": "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier"}})
    write_with_llm(facts, signals, m.period, BRAND, client=FakeClient([quota, reply(good)]), models=["a", "b"], tracker=t)
    assert t.remaining("a") == 0 and t.used("b") == 1

    client = FakeClient([reply(good)])
    r = write_with_llm(facts, signals, m.period, BRAND, client=client, models=["a", "b"], tracker=t)
    assert client.calls == ["b"]  # "a" is not called again today
    assert r.calls[0].status == "skipped"


def test_per_minute_429_does_not_count_or_exhaust(tmp_path):
    m, facts, signals, good = _sample()
    t = UsageTracker(tmp_path / "u.json")
    per_minute = errors.ClientError(429, {"error": {"message": "Quota exceeded: GenerateRequestsPerMinutePerProjectPerModel"}})
    write_with_llm(facts, signals, m.period, BRAND, client=FakeClient([per_minute, reply(good)]), models=["a", "b"], tracker=t)
    assert t.used("a") == 0 and t.remaining("a") > 0
