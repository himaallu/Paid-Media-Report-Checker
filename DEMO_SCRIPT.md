# Demo video script (about 80 seconds)

**Setup before recording**
- `GEMINI_API_KEY` is set and `streamlit run app.py` is open at 1440 px wide, sidebar visible, browser zoom 90–100%.
- Do one full run before recording to warm up: Generate, then refresh the page. The free tier allows about 20 calls per model per day, so don't rehearse 30 times.
- The trap re-uses the summary already written (no second LLM call), so it is instant and costs nothing.
- If Gemini is down, choose "Offline template". The checker and the trap work exactly the same.

---

**0:00–0:10 · The problem** (app open, nothing generated yet)
> "Every week, agencies turn ad exports into client summaries. LLMs make that fast, but one wrong number in a client email costs more trust than the time it saved. So I built a report writer that can't send a number it hasn't verified."

**0:10–0:20 · The data** (point at the data preview)
> "This is two weeks of Meta and Google data for a fictional Dubai coffee chain: six campaigns. pandas computes every metric (CTR, CPC, CPA, ROAS, and week-over-week changes). The LLM never does arithmetic."

**0:20–0:40 · Generate** (click **Generate & verify report**)
> "Gemini gets only the computed metrics as JSON and returns a structured summary, where every number is tied to a metric id. Here it caught the Iced Latte CPA spike, the Reels CTR drop and the Brand Search ROAS winner."

Point at the green banner and the metric row:
> "Then the checker re-reads every number in the text itself and matches it against pandas: twenty-something out of twenty-something verified. You can also see the tokens, latency and cost of the call, which is a fraction of a cent."

**0:40–1:05 · The trap** (turn on **Hallucination trap**, click Generate again)
> "Now I simulate a hallucination: one number in the summary is changed after the model wrote it, with the right metric and the wrong value."

Point at the red banner, then the struck-through number:
> "The report is blocked: not ready to send. It shows the exact sentence, the wrong figure, and the correct value from the source data. The download is now labelled as a draft."

**1:05–1:20 · Close** (scroll to the metrics table, then hover over the download button)
> "Deterministic maths, an LLM for the writing, and a verifier in between. Next steps are live Meta and Google Ads APIs, Arabic summaries and brand-voice templates. The repo has the tests, including this trap case."

---

**Shot list:** landing page → Generate → green banner and metric row → summary (hover over one green number to show its tooltip) → trap toggle → red banner → failing sentence → claim table (failures listed first) → download button.
