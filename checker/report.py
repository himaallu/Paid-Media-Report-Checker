"""HTML rendering: highlighted sentences (shared with the UI) and the downloadable report."""

from __future__ import annotations

from datetime import datetime
from html import escape

from checker.llm_log import totals
from checker.models import SECTIONS
from checker.pipeline import PipelineResult, metrics_table
from checker.verifier import MISMATCH, UNSUPPORTED, VERIFIED, NumberCheck, SentenceCheck

CSS = """
.hm-sum { font-family: -apple-system, Segoe UI, Roboto, sans-serif; line-height: 1.65; font-size: 16px; color: #1f2328; }
.hm-sum h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: #57606a; margin: 18px 0 6px; }
.hm-sum .headline { font-size: 19px; font-weight: 600; }
.hm-sum p { margin: 4px 0; }
.num { padding: 1px 5px; border-radius: 5px; font-weight: 600; white-space: nowrap; }
.num.verified { background: #dafbe1; color: #116329; }
.num.mismatch { background: #ffd8d3; color: #a40e26; text-decoration: line-through; }
.num.unsupported { background: #fff1c2; color: #7a4d00; }
.sent-bad { background: #fff5f5; border-left: 4px solid #cf222e; display: block; padding: 6px 10px; margin: 6px 0; border-radius: 4px; }
.fix { display: block; font-size: 13.5px; color: #a40e26; margin-top: 3px; }
.fix.unsupported { color: #7a4d00; }
"""

STATUS_TITLE = {VERIFIED: "Verified", MISMATCH: "Mismatch", UNSUPPORTED: "Unsupported"}


def _span_start(text: str, check: NumberCheck) -> int:
    """Include a currency prefix directly before the number in the highlight."""
    for prefix in ("AED ", "AED", "$"):
        if text[: check.start].endswith(prefix):
            return check.start - len(prefix)
    return check.start


def sentence_html(sc: SentenceCheck) -> str:
    text, pos, parts = sc.text, 0, []
    for c in sc.checks:
        start = _span_start(text, c)
        parts.append(escape(text[pos:start]))
        tip = STATUS_TITLE[c.status] + (f" · {c.fact_id}" if c.fact_id else "") + (f" · {c.message}" if c.message else "")
        parts.append(f'<span class="num {c.status}" title="{escape(tip)}">{escape(text[start:c.end].strip())}</span>')
        pos = c.end
    parts.append(escape(text[pos:]))
    body = "".join(parts)
    if sc.ok:
        return body
    fixes = []
    for c in sc.checks:
        if c.status == MISMATCH:
            fixes.append(f'<span class="fix">✗ “{escape(c.raw)}” is wrong. {escape(c.message)}</span>')
        elif c.status == UNSUPPORTED:
            fixes.append(f'<span class="fix unsupported">? “{escape(c.raw)}”: {escape(c.message)}</span>')
    return f'<span class="sent-bad">{body}{"".join(fixes)}</span>'


def summary_html(result: PipelineResult) -> str:
    by_section: dict[str, list[SentenceCheck]] = {}
    for sc in result.verification.sentences:
        by_section.setdefault(sc.section, []).append(sc)
    html = [f'<div class="hm-sum"><p class="headline">{sentence_html(by_section["headline"][0])}</p>']
    for key, title in SECTIONS.items():
        items = by_section.get(key, [])
        if not items:
            continue
        html.append(f"<h3>{escape(title)}</h3>")
        if key == "recommendations":
            html.append("<ul>" + "".join(f"<li>{sentence_html(sc)}</li>" for sc in items) + "</ul>")
        else:
            html.extend(f"<p>{sentence_html(sc)}</p>" for sc in items)
    html.append("</div>")
    return "".join(html)


def report_html(result: PipelineResult) -> str:
    v = result.verification
    period = result.metrics.period.label()
    if v.ready:
        stamp = f'<div class="stamp ok">✓ Ready to send · {v.score()}</div>'
    else:
        issues = v.total - v.verified
        stamp = f'<div class="stamp bad">✗ NOT READY TO SEND · {issues} issue(s) · {v.score()}</div>'

    table = metrics_table(result.metrics).reset_index().to_html(index=False, classes="metrics", border=0, escape=True)
    t = totals(result.calls)
    cost = "n/a" if t["cost_usd"] is None else f"${t['cost_usd']:.4f} paid-tier equivalent"
    usage = (
        f"Writer: {escape(result.writer)}"
        + (f" · {t['calls']} LLM call(s), {t['input_tokens']:,} in / {t['output_tokens']:,} out tokens, {t['latency_s']} s, {cost}" if result.calls else "")
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(result.brand)} weekly paid media report</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px; margin: 32px auto; padding: 0 16px; color: #1f2328; background: #fff; }}
h1 {{ font-size: 24px; margin-bottom: 2px; }} .muted {{ color: #57606a; font-size: 14px; }}
.stamp {{ margin: 16px 0; padding: 10px 14px; border-radius: 8px; font-weight: 700; }}
.stamp.ok {{ background: #dafbe1; color: #116329; }} .stamp.bad {{ background: #ffebe9; color: #a40e26; border: 1px solid #cf222e; }}
table.metrics {{ border-collapse: collapse; font-size: 12.5px; width: 100%; margin-top: 8px; }}
table.metrics th, table.metrics td {{ padding: 5px 7px; border-bottom: 1px solid #eaeef2; text-align: right; white-space: nowrap; }}
table.metrics th:first-child, table.metrics td:first-child {{ text-align: left; }}
.wrap {{ overflow-x: auto; }}
{CSS}
</style></head><body>
<h1>{escape(result.brand)} · Weekly paid media report</h1>
<div class="muted">{escape(period)} · generated {datetime.now().strftime("%d %b %Y %H:%M")}</div>
{stamp}
{summary_html(result)}
<h2 style="font-size:18px;margin-top:28px">Campaign metrics (this week)</h2>
<div class="wrap">{table}</div>
<p class="muted" style="margin-top:24px">All figures are computed from the uploaded export. Every number in the summary was checked against them automatically. {usage}</p>
</body></html>"""
