"""Guided demo: the steps, what state each step needs, and the CSS that spotlights a section.

Each step points at one or more page sections (Streamlit containers keyed `sec_<name>`).
Moving between steps can change what the page shows: no report yet, a normal report,
the trap, or the auto-corrected report. `state_for(step)` says which.
"""

from __future__ import annotations

from dataclasses import dataclass

# Page states the tour can put the app in.
NO_REPORT, NORMAL, TRAPPED, CORRECTED = "no_report", "normal", "trapped", "corrected"


@dataclass(frozen=True)
class Step:
    title: str
    body: str  # markdown
    targets: tuple[str, ...]  # section names to spotlight; first one is scrolled to
    state: str
    next_label: str = "Next →"


STEPS: list[Step] = [
    Step(
        "Welcome. Here's what this demo is about",
        "Agencies spend hours every week turning ad-platform exports into client reports. AI can write those reports "
        "in seconds, but it sometimes gets numbers wrong, and **one wrong number in a client email costs more trust than "
        "the time it saved.**\n\n"
        "This prototype shows a safer pattern: **code does the maths, the AI only writes the words, and a checker "
        "verifies every number before the report can be sent.** The tour takes about two minutes and uses made-up data.",
        ("hero",),
        NO_REPORT,
        "Start the tour →",
    ),
    Step(
        "1 · The data",
        "This is a two-week export from Meta and Google Ads for **Dune & Dallah Coffee**, a fictional Dubai coffee chain: "
        "six campaigns and 168 rows of daily spend, clicks, conversions and revenue.\n\n"
        "The tiles show this week against last week. **Python (pandas) calculates every one of these numbers.** "
        "The AI never does arithmetic. In the sidebar you can switch to your own CSV export.",
        ("kpis", "sidebar"),
        NO_REPORT,
        "Generate the report →",
    ),
    Step(
        "2 · The pipeline just ran",
        "The four steps in the header are the whole idea:\n\n"
        "**Compute:** pandas worked out CTR, CPC, CPA, ROAS and week-over-week changes.  \n"
        "**Write:** the AI was given *only* those computed numbers (never the raw data) and wrote a client summary, "
        "tagging every number with the metric it came from.  \n"
        "**Verify:** a checker re-read the finished text and compared every number with the data.  \n"
        "**Send:** only a fully verified report is marked ready.",
        ("hero",),
        NORMAL,
    ),
    Step(
        "3 · The verdict",
        "The ring shows how many numbers in the summary matched the source data. All of them did, so the report is "
        "**ready to send**.\n\n"
        "The small tiles on the right show what the AI call cost: model, tokens, time taken and price. Every call is "
        "logged, because cost and speed matter when a team runs this for dozens of clients every week.",
        ("status",),
        NORMAL,
    ),
    Step(
        "4 · The client summary",
        "This is the email an account manager would send: what changed, what's underperforming, and two or three "
        "recommendations.\n\n"
        "**Every green number has been checked against the data.** Hover over any number to see which metric it "
        "came from. The AI picked up the real story in the data: a CPA spike on the Iced Latte campaign, falling "
        "click-through on Reels, and Brand Search as the ROAS winner.",
        ("summary",),
        NORMAL,
    ),
    Step(
        "5 · Claim-by-claim check",
        "Each row is one number from the summary: what was written, the true value from the data, and the metric it "
        "belongs to.\n\n"
        "The key detail: **the checker doesn't trust the AI's own labels.** It reads the numbers straight out of the "
        "text, so a number the AI got wrong can't hide behind a correct tag. Next, let's see what happens when the "
        "AI gets one wrong.",
        ("claims",),
        NORMAL,
        "Plant a wrong number →",
    ),
    Step(
        "6 · The hallucination trap",
        "We just changed one number in the summary *after* it was written. The metric is right but the value is "
        "wrong, which is exactly what a real AI mistake looks like.\n\n"
        "The checker caught it straight away. The header now says **Blocked**, the ring is red, and the sentence is "
        "highlighted with the wrong figure crossed out and the **correct value** shown underneath. The download is "
        "labelled as an unverified draft, so it can't reach a client by mistake.",
        ("status", "summary"),
        TRAPPED,
        "Auto-correct it →",
    ),
    Step(
        "7 · Auto-correct",
        "Because the checker knows which metric the wrong number was meant to be, it can fix it: it swapped in the "
        "real value and **checked the whole summary again from scratch.** No second AI call was needed.\n\n"
        "The corrected number is shown in **blue**, with a note of what it was, so the account manager can see "
        "exactly what changed before sending.",
        ("status", "summary"),
        CORRECTED,
    ),
    Step(
        "8 · The full picture",
        "Beyond the email, the account manager gets the context to back it up: **ROAS by campaign** against the 1x "
        "break-even line, and every metric with its week-over-week change, coloured green or red depending on "
        "whether the change is good.\n\n"
        "The **LLM calls** tab lists every AI request, and the sidebar counts how many free Gemini calls are left today.",
        ("chart", "tables"),
        CORRECTED,
    ),
    Step(
        "You've seen the whole flow",
        "**Try it yourself:**\n"
        "- Upload your own export in the sidebar (columns: date, platform, campaign, ad_set, spend, impressions, "
        "clicks, conversions, revenue).\n"
        "- Turn the **Hallucination trap** on or off and generate again.\n"
        "- Switch the writer to **Offline template** to see that the checks work without any AI at all.\n\n"
        "This is a prototype. The next steps would be connecting the Meta and Google Ads APIs directly, Arabic "
        "summaries for GCC clients, and brand-voice templates per client.",
        (),
        CORRECTED,
        "Finish tour ✓",
    ),
]


def state_for(step: int) -> str:
    return STEPS[step].state


SPOTLIGHT = """
.st-key-sec_{name} {{
  position: relative;
  outline: 3px solid #0969da;
  outline-offset: 6px;
  border-radius: 12px;
  box-shadow: 0 0 0 10px rgba(9, 105, 218, .10);
  transition: outline-color .3s;
}}
.st-key-sec_{name}::before {{
  content: "{label}";
  position: absolute; top: -18px; left: 10px; z-index: 5;
  background: #0969da; color: #fff; font-size: 12px; font-weight: 700;
  padding: 2px 9px; border-radius: 999px;
}}
"""

SIDEBAR_SPOTLIGHT = """
[data-testid="stSidebar"] { box-shadow: inset 0 0 0 3px #0969da; }
"""

TOUR_BAR_CSS = """
.st-key-tour_bar {
  scroll-margin-top: 90px;
  background: #f3f9ff; border: 1px solid #b6d7ff; border-left: 5px solid #0969da;
  border-radius: 12px; padding: 14px 18px 10px; margin-bottom: 18px;
  box-shadow: 0 6px 18px rgba(9, 105, 218, .12);
}
.st-key-tour_bar p, .st-key-tour_bar li { font-size: 15px; line-height: 1.55; }
.tour-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.tour-title { font-size: 18px; font-weight: 700; color: #0b3d91; margin: 0; }
.tour-count { font-size: 12.5px; color: #57606a; white-space: nowrap; }
.tour-dots { display: flex; gap: 5px; margin: 6px 0 2px; }
.tour-dots span { height: 5px; flex: 1; border-radius: 3px; background: #d0e3fb; }
.tour-dots span.done { background: #0969da; }
"""


def spotlight_css(step: int) -> str:
    """CSS that outlines the sections the current step is about, plus the tour card style."""
    css = [TOUR_BAR_CSS]
    for name in STEPS[step].targets:
        if name == "sidebar":
            css.append(SIDEBAR_SPOTLIGHT)
        else:
            css.append(SPOTLIGHT.format(name=name, label="📍 Guided demo"))
    return "<style>" + "".join(css) + "</style>"


def header_html(step: int) -> str:
    s = STEPS[step]
    dots = "".join(f'<span class="{"done" if i <= step else ""}"></span>' for i in range(len(STEPS)))
    return (
        f'<div class="tour-head"><p class="tour-title">{s.title}</p>'
        f'<span class="tour-count">Step {step + 1} of {len(STEPS)}</span></div>'
        f'<div class="tour-dots">{dots}</div>'
    )


def scroll_js(step: int) -> str:
    """Scrolls the page to the tour card (runs in a zero-height component iframe)."""
    return f"""<script>
// step {step}
setTimeout(() => {{
  try {{
    const el = window.parent.document.querySelector(".st-key-tour_bar");
    if (el) el.scrollIntoView({{behavior: "smooth", block: "start"}});
  }} catch (e) {{}}
}}, 400);
</script>"""


def home_section(step: int) -> str:
    """The section the tour card is shown in: the first target, or the top of the page."""
    targets = [t for t in STEPS[step].targets if t != "sidebar"]
    return targets[0] if targets else "top"
