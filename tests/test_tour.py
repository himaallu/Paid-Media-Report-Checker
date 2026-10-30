"""Guided demo: step definitions, and the tour driven through the real app."""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from checker import tour

APP = Path(__file__).resolve().parent.parent / "app.py"


def test_every_step_targets_a_section_that_exists_in_the_app():
    source = APP.read_text()
    keys = set(re.findall(r'key="sec_(\w+)"', source))
    for step in tour.STEPS:
        for target in step.targets:
            assert target == "sidebar" or target in keys, target
    assert all(step.body and step.title for step in tour.STEPS)


def test_tour_starts_without_a_report_and_ends_corrected():
    states = [tour.state_for(i) for i in range(len(tour.STEPS))]
    assert states[0] == tour.NO_REPORT
    assert tour.NORMAL in states and tour.TRAPPED in states
    assert states[-1] == tour.CORRECTED
    # States only move forward: none -> normal -> trapped -> corrected.
    order = [tour.NO_REPORT, tour.NORMAL, tour.TRAPPED, tour.CORRECTED]
    assert [order.index(s) for s in states] == sorted(order.index(s) for s in states)


def test_spotlight_and_scroll_snippets():
    css = tour.spotlight_css(4)
    assert ".st-key-sec_summary" in css
    assert "stSidebar" in tour.spotlight_css(1)
    assert ".st-key-tour_bar" in tour.scroll_js(3)


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # offline template: no network
    monkeypatch.setenv("GEMINI_USAGE_FILE", str(tmp_path / "usage.json"))
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.query_params["tour"] = "off"  # no welcome pop-up
    return at.run()


def click(at, key):
    next(b for b in at.button if b.key == key).click()
    return at.run()


def test_guided_demo_walks_through_trap_and_correction(app):
    at = next(b for b in app.sidebar.button if "Guided demo" in b.label).click().run()
    assert at.session_state.tour_step == 0
    assert "result" not in at.session_state

    at = click(at, "tour_next")  # 1 · The data
    assert "result" not in at.session_state
    at = click(at, "tour_next")  # 2 · generates the report
    r = at.session_state.result
    assert r.verification.ready and r.trap is None

    for _ in range(4):  # 3, 4, 5, then 6 · the trap
        at = click(at, "tour_next")
    r = at.session_state.result
    assert at.session_state.tour_step == 6
    assert r.trap is not None and not r.verification.ready

    at = click(at, "tour_next")  # 7 · auto-correct
    r = at.session_state.result
    assert r.verification.ready and r.fixes

    at = click(at, "tour_back")  # back to the trap: the correction is undone
    assert not at.session_state.result.verification.ready

    at = click(at, "tour_exit")
    assert "tour_step" not in at.session_state
    assert not at.exception
