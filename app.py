"""Paid Media Report Checker: Streamlit UI.  Run: streamlit run app.py"""

from __future__ import annotations

import hashlib
from io import BytesIO

import pandas as pd
import streamlit as st

from checker.config import has_gemini_key, load_dotenv, load_secrets
from checker.facts import build_facts, build_signals
from checker.llm_log import totals
from checker.metrics import DataError, compute, load_csv
from checker.pipeline import PipelineResult, Written, correct, metrics_table, run, write
from checker.report import CSS, report_html, summary_html
from checker.sample_data import BRAND, OUT as SAMPLE_CSV
from checker.ui import APP_CSS, claims_frame, email_card_html, hero_html, how_it_works_html, kpis, roas_chart, status_html, style_metrics
from checker.usage import UsageTracker
from checker.verifier import VERIFIED
from checker.writer import model_chain

st.set_page_config(page_title="Report Checker", page_icon="✅", layout="wide")
st.html(APP_CSS)

# The key comes from the environment, a local .env file, or Streamlit secrets (see README).
load_dotenv()
load_secrets(st.secrets)
HAS_KEY = has_gemini_key()
tracker = UsageTracker()
DATE_COL = {"date": st.column_config.DateColumn("date", format="D MMM YYYY")}


def render_usage(box) -> None:
    """Gemini requests made today per model, and how many are left on the free tier."""
    rows = tracker.snapshot(model_chain())
    left = sum(int(r["remaining"]) for r in rows)
    with box.container():
        st.subheader("Gemini calls today")
        st.caption(f"**{left} left** across {len(rows)} models · resets at midnight Pacific time (11:00 or 12:00 in Dubai)")
        for r in rows:
            used, limit, remaining = int(r["used"]), int(r["limit"]), int(r["remaining"])
            st.progress(min(1.0, (limit - remaining) / limit), text=f"{r['model']}: {used} used · {remaining} left")
        st.caption("Counted by this app (Google doesn't report the remaining quota). Calls made with the same key elsewhere aren't included.")


# ---------- sidebar ----------
with st.sidebar:
    st.subheader("1 · Data")
    source = st.radio("Campaign export", ["Sample: fictional Dubai coffee chain", "Upload CSV"], label_visibility="collapsed")
    upload = st.file_uploader("CSV export", type="csv") if source == "Upload CSV" else None
    brand = st.text_input("Client name", BRAND)

    st.subheader("2 · Writer")
    writer_choice = st.radio(
        "Summary writer",
        ["Gemini (LLM)", "Offline template"],
        index=0 if HAS_KEY else 1,
        label_visibility="collapsed",
        help="The offline template needs no API key; it's the fallback if the LLM is unavailable.",
    )
    if writer_choice.startswith("Gemini") and not HAS_KEY:
        st.caption("⚠️ GEMINI_API_KEY isn't set, so the offline template will be used.")

    st.subheader("3 · Demo")
    trap = st.toggle("🪤 Hallucination trap", help="Changes one number in the summary after it's written, to show the checker catching it.")

    go = st.button("Generate & verify report", type="primary", width="stretch")
    st.divider()
    usage_box = st.empty()
    render_usage(usage_box)
    st.divider()
    st.download_button("Download sample CSV", SAMPLE_CSV.read_bytes(), "sample_campaigns.csv", "text/csv", width="stretch")

hero_box = st.empty()


def load_data() -> tuple[pd.DataFrame, bytes] | None:
    raw = upload.getvalue() if upload is not None else (SAMPLE_CSV.read_bytes() if source.startswith("Sample") else None)
    if raw is None:
        return None
    return load_csv(BytesIO(raw)), raw


try:
    loaded = load_data()
except DataError as exc:
    hero_box.html(hero_html(None))
    st.error(f"That file can't be used: {exc}")
    st.stop()

if loaded is None:
    hero_box.html(hero_html(None))
    st.info("Upload a CSV with columns: date, platform, campaign, ad_set, spend, impressions, clicks, conversions, revenue.")
    st.stop()

df, raw = loaded
go = go or st.session_state.pop("main_go", False)  # the landing page has its own Generate button (handy on phones)

if go:
    use_llm = writer_choice.startswith("Gemini") and HAS_KEY
    # Cache the written summary per (data, client, writer), so toggling the trap doesn't spend another LLM call.
    key = hashlib.sha256(raw + brand.encode() + str(use_llm).encode()).hexdigest()
    cache: dict[str, Written] = st.session_state.setdefault("written", {})
    try:
        with st.spinner("Computing metrics, writing the summary and checking every number…"):
            written = cache.get(key)
            reused = written is not None
            if written is None:
                m = compute(df)
                written = write(m, build_facts(m), build_signals(m), brand, use_llm, tracker=tracker)
                if not written.notice:
                    cache[key] = written
            st.session_state["result"] = run(df, brand, trap=trap, written=written)
            st.session_state["reused"] = reused
        render_usage(usage_box)
    except DataError as exc:
        hero_box.html(hero_html(None))
        st.error(f"That file can't be used: {exc}")
        st.stop()

result: PipelineResult | None = st.session_state.get("result")
hero_box.html(hero_html(result))

# ---------- landing ----------
if result is None:
    st.html(how_it_works_html())
    st.button(
        "Generate & verify report",
        type="primary",
        key="main_generate",
        on_click=lambda: st.session_state.update(main_go=True),
        help="Uses the data, writer and trap settings in the sidebar.",
    )
    m = compute(df)
    st.markdown(f"#### This week at a glance · {m.period.label()}")
    for col, (label, value, delta, colour) in zip(st.columns(5, border=True), kpis(m)):
        col.metric(label, value, delta, delta_color=colour)
    st.markdown("#### Data preview")
    st.caption(f"{len(df):,} rows · {df['campaign'].nunique()} campaigns · {df['platform'].nunique()} platforms. Settings are in the sidebar.")
    st.dataframe(df.head(20), width="stretch", hide_index=True, column_config=DATE_COL)
    st.stop()

v = result.verification

# ---------- status ----------
st.html(status_html(result, totals(result.calls), bool(st.session_state.get("reused"))))
fixable = [c for c in v.checks if c.status == "mismatch"]
if fixable and not result.fixes:
    st.button(
        f"✨ Auto-correct {len(fixable)} number{'s' if len(fixable) != 1 else ''} from the source data",
        type="primary",
        on_click=lambda: st.session_state.update(result=correct(result)),
        help="Swaps each wrong number for the value pandas computed, then runs the full check again. No LLM call.",
    )
if result.fixes and not v.ready:
    st.warning("Some numbers aren't linked to any metric, so they can't be corrected automatically. Edit those sentences by hand.", icon="✋")
if result.notice:
    st.warning(result.notice, icon="⚠️")
if result.trap:
    caught = bool(result.fixes) or any(c.status != VERIFIED and c.fact_id == result.trap.fact_id for c in v.checks)
    fixed = any(f.fact_id == result.trap.fact_id and f.kind == "value" for f in result.fixes)
    st.info(
        f"**Trap mode:** after the summary was written, **{result.trap.original}** was changed to "
        f"**{result.trap.injected}** (`{result.trap.fact_id}`). Caught by the checker: **{'yes' if caught else 'NO'}**."
        + (f" Auto-corrected back to **{result.trap.original}**." if fixed else ""),
        icon="🪤",
    )

# ---------- KPIs ----------
st.markdown(f"#### This week at a glance · {result.metrics.period.label()}")
for col, (label, value, delta, colour) in zip(st.columns(5, border=True), kpis(result.metrics)):
    col.metric(label, value, delta, delta_color=colour)

# ---------- summary + checks ----------
left, right = st.columns([3, 2], gap="large")
with left:
    st.markdown("#### Client summary")
    st.html(f"<style>{CSS}</style>{email_card_html(result, summary_html(result))}")

    html = report_html(result)
    slug = "".join(ch if ch.isalnum() else "-" for ch in result.brand.lower()).strip("-")
    name = f"{slug}-weekly-report.html" if v.ready else f"{slug}-weekly-report-DRAFT-NOT-VERIFIED.html"
    d1, d2 = st.columns(2)
    d1.download_button(
        "⬇ Download report" if v.ready else "⬇ Download draft (not verified)",
        html,
        name,
        "text/html",
        type="primary" if v.ready else "secondary",
        width="stretch",
    )
    d2.download_button("⬇ Metrics CSV", metrics_table(result.metrics).to_csv().encode(), f"{slug}-metrics.csv", "text/csv", width="stretch")

with right:
    st.markdown("#### Claim-by-claim check")
    claims = claims_frame(result)
    only_issues = st.toggle("Show only issues", value=not v.ready, disabled=v.ready)
    if only_issues:
        claims = claims[~claims["Status"].str.startswith("✅")]
    st.dataframe(
        claims.style.apply(lambda r: ["background-color: #ffebe9" if not r["Status"].startswith("✅") else ""] * len(r), axis=1),
        width="stretch",
        hide_index=True,
        height=min(36 * (len(claims) + 1) + 4, 420),
        column_config={"Note": st.column_config.TextColumn(width="medium")},
    )

    st.markdown("#### ROAS by campaign · this week")
    st.altair_chart(roas_chart(result.metrics), width="stretch")
    st.caption("Hover a bar for spend, revenue and the week-over-week change. Below the dashed line, a campaign earns less than it spends.")

# ---------- tables ----------
st.markdown("#### Metrics · this week, with week-over-week change")
tab_c, tab_p, tab_t, tab_calls, tab_raw = st.tabs(["Campaigns", "Platforms", "Total", "LLM calls", "Raw data"])
tab_c.dataframe(style_metrics(metrics_table(result.metrics, "campaign")), width="stretch")
tab_p.dataframe(style_metrics(metrics_table(result.metrics, "platform")), width="stretch")
tab_t.dataframe(style_metrics(metrics_table(result.metrics, "total")), width="stretch")
tab_c.caption("Green = better, red = worse (for CPA and CPC, lower is better). Spend changes are neutral.")
with tab_calls:
    if result.calls:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Model": c.model,
                        "Status": c.status,
                        "Latency (s)": round(c.latency_s, 2),
                        "Input tokens": c.input_tokens,
                        "Output tokens": c.output_tokens,
                        "of which thinking": c.thinking_tokens,
                        "Cost (USD)": "n/a" if c.cost_usd is None else f"{c.cost_usd:.5f}",
                        "Note": c.note,
                    }
                    for c in result.calls
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.write("No LLM calls: the offline template wrote this summary.")
tab_raw.dataframe(df, width="stretch", hide_index=True, column_config=DATE_COL)
