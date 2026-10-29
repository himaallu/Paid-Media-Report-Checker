"""Paid Media Report Checker: Streamlit UI.  Run: streamlit run app.py"""

from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from checker.config import has_gemini_key, load_dotenv, load_secrets
from checker.facts import build_facts, build_signals
from checker.llm_log import totals
from checker.metrics import DataError, compute, load_csv
from checker.pipeline import PipelineResult, Written, metrics_table, run, write
from checker.report import CSS, report_html, summary_html
from checker.sample_data import BRAND, OUT as SAMPLE_CSV
from checker.usage import UsageTracker
from checker.verifier import MISMATCH, UNSUPPORTED, VERIFIED
from checker.writer import model_chain

st.set_page_config(page_title="Report Checker", page_icon="✅", layout="wide")

STATUS_ICON = {VERIFIED: "✅ Verified", MISMATCH: "❌ Mismatch", UNSUPPORTED: "⚠️ Unsupported"}
# The key comes from the environment, a local .env file, or Streamlit secrets (see README).
load_dotenv()
load_secrets(st.secrets)
HAS_KEY = has_gemini_key()
tracker = UsageTracker()


def render_usage(box) -> None:
    """Gemini requests made today per model, and how many are left on the free tier."""
    rows = tracker.snapshot(model_chain())
    left = sum(int(r["remaining"]) for r in rows)
    with box.container():
        st.header("Gemini calls today")
        st.caption(f"**{left} left** across {len(rows)} models · resets at midnight Pacific time (11:00 or 12:00 in Dubai)")
        for r in rows:
            used, limit, remaining = int(r["used"]), int(r["limit"]), int(r["remaining"])
            st.progress(min(1.0, (limit - remaining) / limit), text=f"{r['model']}: {used} used · {remaining} left")
        st.caption("Counted by this app (Google doesn't report the remaining quota). Calls made with the same key elsewhere aren't included.")

# ---------- sidebar ----------
with st.sidebar:
    st.header("1 · Data")
    source = st.radio("Campaign export", ["Sample: fictional Dubai coffee chain", "Upload CSV"], label_visibility="collapsed")
    upload = st.file_uploader("CSV export", type="csv") if source == "Upload CSV" else None
    brand = st.text_input("Client name", BRAND)

    st.header("2 · Writer")
    writer_choice = st.radio(
        "Summary writer",
        ["Gemini (LLM)", "Offline template"],
        index=0 if HAS_KEY else 1,
        label_visibility="collapsed",
        help="The offline template needs no API key; it's the fallback if the LLM is unavailable.",
    )
    if writer_choice.startswith("Gemini") and not HAS_KEY:
        st.caption("⚠️ GEMINI_API_KEY isn't set, so the offline template will be used.")

    st.header("3 · Demo")
    trap = st.toggle("🪤 Hallucination trap", help="Changes one number in the summary after it's written, to show the checker catching it.")

    go = st.button("Generate & verify report", type="primary", use_container_width=True)
    st.divider()
    usage_box = st.empty()
    render_usage(usage_box)
    st.divider()
    st.download_button("Download sample CSV", SAMPLE_CSV.read_bytes(), "sample_campaigns.csv", "text/csv", use_container_width=True)

# ---------- header ----------
st.title("Paid Media Report Checker")
st.caption("Weekly ad export → client-ready summary → every number checked against the source data before it can be sent.")


def load_data() -> tuple[pd.DataFrame, bytes] | None:
    raw = upload.getvalue() if upload is not None else (SAMPLE_CSV.read_bytes() if source.startswith("Sample") else None)
    if raw is None:
        return None
    from io import BytesIO

    return load_csv(BytesIO(raw)), raw


try:
    loaded = load_data()
except DataError as exc:
    st.error(f"That file can't be used: {exc}")
    st.stop()

if loaded is None:
    st.info("Upload a CSV with columns: date, platform, campaign, ad_set, spend, impressions, clicks, conversions, revenue.")
    st.stop()

df, raw = loaded

if go:
    use_llm = writer_choice.startswith("Gemini") and HAS_KEY
    # Cache the written summary per (data, client, writer), so toggling the trap doesn't spend another LLM call.
    key = hashlib.sha256(raw + brand.encode() + str(use_llm).encode()).hexdigest()
    cache: dict[str, Written] = st.session_state.setdefault("written", {})
    try:
        with st.spinner("Computing metrics and writing the summary…"):
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
        st.error(f"That file can't be used: {exc}")
        st.stop()

result: PipelineResult | None = st.session_state.get("result")
if result is None:
    st.markdown(
        "**How it works:** pandas computes every metric → the LLM writes a summary quoting only those numbers → "
        "the checker re-reads every number in the text and matches it against the computed metrics."
    )
    st.subheader("Data preview")
    st.dataframe(df.head(20), use_container_width=True, hide_index=True)
    st.stop()

v = result.verification

# ---------- status ----------
if v.ready:
    st.success(f"### ✅ Ready to send  ·  {v.score()}")
else:
    issues = v.total - v.verified
    st.error(f"### ⛔ Not ready to send  ·  {v.score()}  ·  {issues} issue(s) highlighted below")

if result.notice:
    st.warning(result.notice)
if result.trap:
    caught = any(c.status != VERIFIED and c.fact_id == result.trap.fact_id for c in v.checks)
    st.info(
        f"🪤 **Trap mode:** after the summary was written, **{result.trap.original}** was changed to "
        f"**{result.trap.injected}** ({result.trap.fact_id}). Caught by the checker: **{'yes' if caught else 'NO'}**."
    )

t = totals(result.calls)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Claims verified", f"{v.verified}/{v.total}")
c2.metric("Writer", "Template" if result.writer == "offline template" else "Gemini", help=f"Written by: {result.writer}")
c3.metric("Tokens (in / out)", f"{t['input_tokens']:,} / {t['output_tokens']:,}" if result.calls else "–")
c4.metric("LLM latency", f"{t['latency_s']} s" if result.calls else "–")
c5.metric("Cost", "–" if not result.calls else ("n/a" if t["cost_usd"] is None else f"${t['cost_usd']:.4f}"),
          help="Paid-tier equivalent at list price; the free tier costs $0.")
if st.session_state.get("reused") and result.calls:
    st.caption("Summary reused from the previous run of this data (no new LLM call); usage shown is from that call.")

# ---------- summary + checks ----------
left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader(f"Client summary · {result.metrics.period.label()}")
    st.html(f"<style>{CSS}</style>{summary_html(result)}")
    st.caption("🟩 verified · 🟥 wrong value (correct value shown) · 🟨 number not linked to any metric. Hover a number for details.")

with right:
    st.subheader("Claim-by-claim check")
    rows = [
        {
            "Status": STATUS_ICON[c.status],
            "Written": c.raw,
            "Source value": c.expected or "–",
            "Metric": c.fact_id or "–",
            "Note": c.message,
        }
        for c in sorted(v.checks, key=lambda c: c.status == VERIFIED)  # failures first
    ]
    claims = pd.DataFrame(rows)
    st.dataframe(
        claims.style.apply(lambda r: ["background-color: #ffebe9" if not r["Status"].startswith("✅") else ""] * len(r), axis=1),
        use_container_width=True,
        hide_index=True,
        height=min(38 * (len(rows) + 1), 520),
    )

# ---------- downloads ----------
html = report_html(result)
slug = "".join(ch if ch.isalnum() else "-" for ch in result.brand.lower()).strip("-")
name = f"{slug}-weekly-report.html" if v.ready else f"{slug}-weekly-report-DRAFT-NOT-VERIFIED.html"
d1, d2, _ = st.columns([1, 1, 2])
d1.download_button(
    "⬇ Download report" if v.ready else "⬇ Download draft (not verified)",
    html,
    name,
    "text/html",
    type="primary" if v.ready else "secondary",
    use_container_width=True,
)
d2.download_button("⬇ Metrics CSV", metrics_table(result.metrics).to_csv().encode(), f"{slug}-metrics.csv", "text/csv", use_container_width=True)

# ---------- tables ----------
st.subheader("Metrics (this week vs last week)")
tab_c, tab_p, tab_t, tab_calls, tab_raw = st.tabs(["Campaigns", "Platforms", "Total", "LLM calls", "Raw data"])
tab_c.dataframe(metrics_table(result.metrics, "campaign"), use_container_width=True)
tab_p.dataframe(metrics_table(result.metrics, "platform"), use_container_width=True)
tab_t.dataframe(metrics_table(result.metrics, "total"), use_container_width=True)
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
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No LLM calls: the offline template wrote this summary.")
tab_raw.dataframe(df, use_container_width=True, hide_index=True)
