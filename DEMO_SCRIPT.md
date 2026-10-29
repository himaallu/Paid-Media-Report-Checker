# Demo video script (about 85 seconds)

## Before you record

- Open the deployed app (your `*.streamlit.app` link), or run `streamlit run app.py` locally with `GEMINI_API_KEY` in `.env`.
- Use a desktop browser about 1440 px wide, with the sidebar open and zoom at 90–100%. Hide your bookmarks bar.
- In the sidebar: **Sample** data, client **Dune & Dallah Coffee**, writer **Gemini (LLM)**, trap **off**.
- Check **Gemini calls today** in the sidebar. Keep at least 5 left: a run uses 1 call, or 2 if the model has to retry.
- Do one practice run, then refresh the page so you start on the landing screen. On Streamlit Cloud the app sleeps when idle, so open it a minute before recording.
- The trap reuses the summary you've already generated, so it's instant and doesn't use a call. Don't change the client name or writer between the two runs, or it will call Gemini again.
- Backup plan: if Gemini is slow or out of quota, the app falls back to the offline template and shows a yellow note. Switch the writer to **Offline template** and carry on; the checker and the trap work the same way.

The Gemini wording changes from run to run, so the exact numbers you read out may differ. Read whatever is on screen; the lines below are a guide.

---

## Script

**0:00–0:12 · The problem** (landing screen: the green header and the four step cards)
> "Every week, agencies turn ad-platform exports into client summaries. An LLM can write one in seconds, but one wrong number in a client email costs more trust than the time it saved. So I built a report writer that can't send a number it hasn't verified."

Run the cursor along the four steps in the header: Compute, Write, Verify, Send.

**0:12–0:22 · The data** (scroll slightly to **This week at a glance**)
> "This is two weeks of Meta and Google Ads data for a fictional Dubai coffee chain: six campaigns. Every metric here (spend, ROAS, CPA, week-over-week change) is calculated in pandas. The LLM never does arithmetic."

**0:22–0:45 · Generate** (click **Generate & verify report**)

While it runs (a few seconds):
> "Gemini only sees the computed metrics, as JSON. It writes the summary and tags every number with the metric it came from."

When it finishes, point at the header (all four steps green), then the score ring:
> "Then the checker ignores those tags. It reads every number out of the text itself and matches it against the source data: all of them verified, ready to send."

Point at the chips on the right of the status card:
> "Every call is logged: model, tokens, latency and cost. That's a fraction of a cent."

Point at the email-style summary, then hover over one green number to show its tooltip:
> "It's written like a client email: what changed, what's underperforming, and what to do. It picked up the Iced Latte CPA spike, the Reels CTR drop and Brand Search as the ROAS winner."

**0:45–1:08 · The trap** (in the sidebar, turn on **Hallucination trap**, then click **Generate & verify report** again)
> "Now I simulate a hallucination: after the model has written the summary, one number is changed. It keeps the right metric but gets the wrong value."

Point at the header (Verify and Send are now red, "Blocked"), then the red score ring:
> "Caught straight away. The report is blocked: not ready to send."

Point at the highlighted sentence, with the struck-through number and the correct value underneath:
> "It shows the exact sentence, the wrong figure, and the correct value from the data."

Point at the claim table on the right (it now shows only the issue), then the button that says **Download draft (not verified)**:
> "The claim table goes straight to the problem, and the download is labelled as an unverified draft, so it can't go to a client by mistake."

**1:08–1:25 · Close** (scroll to the **ROAS by campaign** chart, then the coloured metrics table)
> "The account manager still gets the full picture: ROAS against break-even, and every week-over-week change, colour-coded. So the maths is deterministic, the LLM does the writing, and a verifier sits in between. Next I'd connect the Meta and Google Ads APIs and add Arabic summaries and brand-voice templates. The repo includes tests for all of this, including the trap."

---

## Shot list

1. Landing screen: header steps → the four step cards → KPI tiles
2. Click **Generate & verify report** → header turns green → 28/28-style score ring → usage chips
3. Email summary → hover over one green number (tooltip)
4. Sidebar: **Hallucination trap** on → Generate again
5. Header shows "Blocked" → red ring → highlighted sentence with the correct value
6. Claim table (issues only) → **Download draft (not verified)** button
7. ROAS chart → coloured metrics table → end

## If something goes wrong

| What you see | What to do |
| --- | --- |
| Yellow note "LLM unavailable … used the offline template" | Keep going; the rest of the demo is identical. Mention that the app never stops working. |
| A sentence highlighted on the first (non-trap) run | That's the checker catching a real Gemini mistake. Point it out: it's an even better demo. Then turn the trap on as planned. |
| App shows "waking up" on Streamlit Cloud | Wait 30–60 seconds; open the app before you start recording next time. |
| Gemini calls left reads 0 | Switch the writer to **Offline template**. The count resets at midnight Pacific time (11:00 or 12:00 in Dubai). |
