"""LLM writer with a scripted fake Gemini client (no network)."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from checker.facts import build_facts, build_signals
from checker.metrics import compute, load_csv
from checker.offline_writer import write_offline
from checker.pipeline import run
from checker.sample_data import BRAND, OUT
from checker.writer import WriterError, build_payload, write_with_llm


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def reply(text, prompt=1000, out=200, thinking=100):
    usage = SimpleNamespace(prompt_token_count=prompt, candidates_token_count=out, thoughts_token_count=thinking)
    return SimpleNamespace(text=text, usage_metadata=usage)


@pytest.fixture(scope="module")
def sample():
    m = compute(load_csv(OUT))
    facts, signals = build_facts(m), build_signals(m)
    return m, facts, signals, write_offline(facts, signals, BRAND).model_dump_json()


def test_valid_reply_is_parsed_and_logged(sample):
    m, facts, signals, good = sample
    client = FakeClient([reply(good)])
    r = write_with_llm(facts, signals, m.period, BRAND, client=client, models=["gemini-3-flash-preview"])
    assert r.model == "gemini-3-flash-preview"
    (call,) = r.calls
    assert (call.status, call.input_tokens, call.output_tokens, call.thinking_tokens) == ("ok", 1000, 300, 100)
    assert call.cost_usd == pytest.approx((1000 * 0.50 + 300 * 3.00) / 1_000_000)
    assert call.latency_s >= 0


def test_invalid_json_gets_one_retry(sample):
    m, facts, signals, good = sample
    client = FakeClient([reply("not json"), reply(good)])
    r = write_with_llm(facts, signals, m.period, BRAND, client=client, models=["gemini-3-flash-preview"])
    assert [c.status for c in r.calls] == ["invalid_output", "ok"]


def test_rate_limit_moves_to_next_model(sample):
    m, facts, signals, good = sample
    client = FakeClient([errors.ClientError(429, {"error": {"message": "quota"}}), reply(good)])
    r = write_with_llm(facts, signals, m.period, BRAND, client=client, models=["model-a", "model-b"])
    assert client.calls == ["model-a", "model-b"]
    assert r.model == "model-b"
    assert r.calls[0].status == "rate_limited"
    assert r.calls[1].cost_usd is None  # unknown price shows n/a


def test_all_models_failing_raises_with_the_call_log(sample):
    m, facts, signals, _ = sample
    client = FakeClient([reply("bad"), reply("still bad")])
    with pytest.raises(WriterError) as exc:
        write_with_llm(facts, signals, m.period, BRAND, client=client, models=["model-a"])
    assert [c.status for c in exc.value.calls] == ["invalid_output", "invalid_output"]


def test_pipeline_falls_back_to_offline_template():
    df = load_csv(OUT)
    client = FakeClient([errors.ServerError(503, {"error": {"message": "overloaded"}})] * 3)
    r = run(df, BRAND, use_llm=True, client=client)
    assert r.writer == "offline template"
    assert "offline template" in r.notice
    assert r.verification.ready


def test_payload_holds_facts_not_raw_rows(sample):
    m, facts, signals, _ = sample
    payload = build_payload(facts, signals, m.period, BRAND)
    assert "campaign.iced_spanish_latte_launch.cpa.current" in payload
    assert "Lookalike 1% UAE" not in payload  # ad-set rows never reach the model
