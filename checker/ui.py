"""HTML pieces and the chart for the Streamlit UI (kept out of app.py for readability)."""

from __future__ import annotations

from html import escape

import altair as alt
import pandas as pd

from checker.facts import fmt
from checker.metrics import MetricsResult
from checker.pipeline import PipelineResult
from checker.verifier import VERIFIED

INK = "#1f2328"
MUTED = "#57606a"
GOOD = "#116329"
BAD = "#a40e26"
SERIES = "#2a78d6"  # categorical slot 1 of the reference palette

APP_CSS = """
<style>
.block-container, [data-testid="stMainBlockContainer"] { padding-top: 4rem !important; max-width: 1280px; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div { font-size: 1.55rem !important; }
[data-testid="stMetricLabel"] p { font-size: 0.9rem; color: #57606a; }
h1, h2, h3 { letter-spacing: -0.01em; }
.hero { background: linear-gradient(135deg, #0b6e4f 0%, #0d4f3c 100%); color: #fff; border-radius: 16px; padding: 22px 26px; margin-bottom: 18px; }
.hero h1 { color: #fff; font-size: 30px; margin: 0 0 4px; padding: 0; }
.hero p { margin: 0; opacity: .88; font-size: 15px; }
.steps { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.step { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22); border-radius: 999px; padding: 4px 12px; font-size: 13px; white-space: nowrap; }
.step.ok { background: #dafbe1; color: #116329; border-color: #dafbe1; font-weight: 600; }
.step.bad { background: #ffebe9; color: #a40e26; border-color: #ffebe9; font-weight: 600; }
.arrow { opacity: .6; align-self: center; font-size: 13px; }

.status { display: flex; align-items: center; gap: 22px; border-radius: 14px; padding: 18px 22px; margin: 4px 0 14px; border: 1px solid; flex-wrap: wrap; }
.status.ok { background: #f0fbf3; border-color: #a6e3b5; }
.status.bad { background: #fff5f5; border-color: #f5a3a9; }
.ring { --p: 100; width: 86px; height: 86px; border-radius: 50%; display: grid; place-items: center; flex: none;
        background: conic-gradient(var(--c) calc(var(--p) * 1%), #e6e9ec 0); }
.ring span { width: 68px; height: 68px; border-radius: 50%; background: #fff; display: grid; place-items: center; font-weight: 700; font-size: 18px; color: #1f2328; }
.status .title { font-size: 22px; font-weight: 700; margin: 0; }
.status.ok .title { color: #116329; } .status.bad .title { color: #a40e26; }
.status .sub { color: #57606a; margin: 2px 0 0; font-size: 14.5px; }
.status .main { flex: 1 1 280px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; flex: 1 1 260px; justify-content: flex-end; }
.chip { background: #fff; border: 1px solid #d8dee4; border-radius: 8px; padding: 6px 10px; font-size: 12.5px; color: #57606a; line-height: 1.25; }
.chip b { display: block; color: #1f2328; font-size: 14px; }

.card { background: #fff; border: 1px solid #d8dee4; border-radius: 14px; padding: 18px 22px; box-shadow: 0 1px 3px rgba(31,35,40,.06); }
.email-head { border-bottom: 1px solid #eaeef2; padding-bottom: 10px; margin-bottom: 8px; font-size: 13.5px; color: #57606a; }
.email-head b { color: #1f2328; font-weight: 600; }
.legend { font-size: 12.5px; color: #57606a; margin-top: 10px; }
.legend .num { font-size: 12px; }

.how { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 6px 0 18px; }
.how .card h4 { margin: 0 0 4px; font-size: 15px; }
.how .card p { margin: 0; color: #57606a; font-size: 14px; }
.how .n { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: #0b6e4f; color: #fff; font-size: 13px; font-weight: 700; margin-bottom: 8px; }
</style>
"""

STEPS = [("compute", "① Compute · pandas"), ("write", "② Write · LLM"), ("verify", "③ Verify every number"), ("send", "④ Send")]


def hero_html(result: PipelineResult | None) -> str:
    states: dict[str, tuple[str, str]] = {}
    if result is not None:
        v = result.verification
        writer = "Gemini" if result.writer != "offline template" else "template"
        states = {
            "compute": ("ok", "① Computed ✓"),
            "write": ("ok", f"② Written by {writer} ✓"),
            "verify": ("ok" if v.ready else "bad", f"③ {v.verified}/{v.total} verified" + (" ✓" if v.ready else " ✗")),
            "send": ("ok" if v.ready else "bad", "④ Ready to send ✓" if v.ready else "④ Blocked"),
        }
    chips = []
    for key, label in STEPS:
        cls, text = states.get(key, ("", label))
        chips.append(f'<span class="step {cls}">{escape(text)}</span>')
    steps = '<span class="arrow">→</span>'.join(chips)
    return (
        '<div class="hero"><h1>Paid Media Report Checker</h1>'
        "<p>Weekly ad export → client-ready summary. Every number is checked against the source data before it can be sent.</p>"
        f'<div class="steps">{steps}</div></div>'
    )


def status_html(result: PipelineResult, totals: dict, reused: bool) -> str:
    v = result.verification
    pct = round(100 * v.verified / v.total) if v.total else 0
    issues = v.total - v.verified
    if v.ready:
        cls, color, title = "ok", "#1a7f37", "Ready to send"
        sub = f"All {v.total} numbers in the summary match the source data."
    else:
        cls, color, title = "bad", "#cf222e", "Not ready to send"
        sub = f"{issues} number{'s' if issues != 1 else ''} in the summary {'don’t' if issues != 1 else 'doesn’t'} match the source data. The failing sentence is highlighted below with the correct value."

    def chip(label: str, value: str) -> str:
        return f'<div class="chip">{escape(label)}<b>{escape(value)}</b></div>'

    if result.calls:
        cost = "n/a" if totals["cost_usd"] is None else f"${totals['cost_usd']:.4f}"
        chips = [
            chip("Writer", result.writer),
            chip("Tokens in / out", f"{totals['input_tokens']:,} / {totals['output_tokens']:,}"),
            chip("Latency", f"{totals['latency_s']} s"),
            chip("Cost (paid-tier eq.)", cost),
        ]
        if reused:
            chips.append(chip("LLM call", "reused (no new call)"))
    else:
        chips = [chip("Writer", "Offline template"), chip("LLM calls", "none")]

    return (
        f'<div class="status {cls}"><div class="ring" style="--p:{pct};--c:{color}"><span>{v.verified}/{v.total}</span></div>'
        f'<div class="main"><p class="title">{title}</p><p class="sub">{escape(sub)}</p></div>'
        f'<div class="chips">{"".join(chips)}</div></div>'
    )


def email_card_html(result: PipelineResult, body_html: str) -> str:
    period = result.metrics.period.label()
    legend = (
        '<div class="legend"><span class="num verified">verified</span> '
        '<span class="num mismatch" style="text-decoration:none">wrong value</span> '
        '<span class="num unsupported">not linked to a metric</span> · hover a number for its source</div>'
    )
    return (
        '<div class="card"><div class="email-head">'
        f"<div><b>To:</b> {escape(result.brand)} marketing team</div>"
        f"<div><b>Subject:</b> Weekly paid media performance · {escape(period)}</div></div>"
        f"{body_html}{legend}</div>"
    )


def how_it_works_html() -> str:
    cards = [
        ("Compute", "pandas calculates CTR, CPC, CPA, ROAS, conversion rate and week-over-week change. The LLM never does arithmetic."),
        ("Write", "Gemini gets only the computed metrics as JSON and returns a structured summary, tagging every number with its metric."),
        ("Verify", "The checker re-reads every number in the text and matches it against the source data, at the precision written."),
        ("Send", "Only a fully verified report is marked ready. Anything else is blocked, with the wrong number and its correct value shown."),
    ]
    items = "".join(
        f'<div class="card"><span class="n">{i}</span><h4>{escape(t)}</h4><p>{escape(d)}</p></div>' for i, (t, d) in enumerate(cards, 1)
    )
    return f'<div class="how">{items}</div>'


# ---- KPI tiles ----

KPIS = [("spend", "Spend", "off"), ("revenue", "Revenue", "normal"), ("roas", "ROAS", "normal"), ("cpa", "CPA", "inverse"), ("conversions", "Conversions", "normal")]


def kpis(m: MetricsResult) -> list[tuple[str, str, str | None, str]]:
    """(label, value, delta, delta_color) for st.metric. CPA going up is bad, so its colour is inverted."""
    out = []
    for metric, label, colour in KPIS:
        cur = m.value("total", "All campaigns", metric, "current")
        wow = m.value("total", "All campaigns", metric, "wow_pct")
        unit = {"spend": "aed", "revenue": "aed", "cpa": "aed", "roas": "x"}.get(metric, "count")
        delta = None if pd.isna(wow) else f"{fmt(wow, 'pct_change')} WoW"
        out.append((label, fmt(cur, unit, metric), delta, colour))
    return out


# ---- chart ----


def roas_chart(m: MetricsResult) -> alt.Chart:
    """ROAS by campaign this week, single series, with the 1x break-even line."""
    wide = m.wide("campaign").reset_index()
    df = pd.DataFrame(
        {
            "Campaign": wide["entity"],
            "Platform": wide["platform"],
            "ROAS": wide["roas"],
            "ROAS label": [fmt(x, "x") for x in wide["roas"]],
            "WoW": [("–" if pd.isna(x) else fmt(x, "pct_change")) for x in wide["roas_wow_pct"]],
            "Spend": [fmt(x, "aed", "spend") for x in wide["spend"]],
            "Revenue": [fmt(x, "aed", "revenue") for x in wide["revenue"]],
        }
    ).sort_values("ROAS", ascending=False)
    order = list(df["Campaign"])
    y = alt.Y("Campaign:N", sort=order, title=None, axis=alt.Axis(labelLimit=220, labelColor=INK, labelFontSize=12, ticks=False, domain=False))
    tooltip = ["Campaign", "Platform", alt.Tooltip("ROAS label", title="ROAS"), alt.Tooltip("WoW", title="ROAS WoW"), "Spend", "Revenue"]

    bars = (
        alt.Chart(df)
        .mark_bar(color=SERIES, cornerRadiusEnd=4, height=18)
        .encode(x=alt.X("ROAS:Q", title="ROAS (revenue ÷ spend)", axis=alt.Axis(grid=True, gridColor="#eef1f4", labelColor=MUTED, titleColor=MUTED, domain=False, tickCount=5)), y=y, tooltip=tooltip)
    )
    labels = bars.mark_text(align="left", dx=5, color=INK, fontSize=12).encode(text="ROAS label")
    breakeven = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(color=MUTED, strokeDash=[4, 3], strokeWidth=1.5).encode(x="x:Q")
    breakeven_label = (
        alt.Chart(pd.DataFrame({"x": [1.0], "t": ["break-even 1x"]}))
        .mark_text(align="left", dx=4, dy=-6, color=MUTED, fontSize=11)
        .encode(x="x:Q", y=alt.value(0), text="t")
    )
    return (bars + labels + breakeven + breakeven_label).properties(height=44 * len(df)).configure_view(stroke=None)


# ---- metrics table colouring ----

INVERSE = {"CPA WoW", "CPC WoW"}  # going up is bad


def style_metrics(table: pd.DataFrame):  # returns a pandas Styler
    def colour(col: pd.Series) -> list[str]:
        if not col.name.endswith("WoW"):
            return [""] * len(col)
        out = []
        for v in col:
            s = str(v)
            if not s or s == "–" or s.startswith(("+0.0", "-0.0")):
                out.append("")
                continue
            up = s.startswith("+")
            good = (not up) if col.name in INVERSE else up
            if col.name == "Spend WoW":
                out.append(f"color: {MUTED}")
            else:
                out.append(f"color: {GOOD if good else BAD}; font-weight: 600")
        return out

    return table.style.apply(colour, axis=0)


def claims_frame(result: PipelineResult) -> pd.DataFrame:
    icon = {"verified": "✅ Verified", "mismatch": "❌ Mismatch", "unsupported": "⚠️ Unsupported"}
    rows = [
        {"Status": icon[c.status], "Written": c.raw, "Source value": c.expected or "–", "Metric": c.fact_id or "–", "Note": c.message}
        for c in sorted(result.verification.checks, key=lambda c: c.status == VERIFIED)  # failures first
    ]
    return pd.DataFrame(rows)
