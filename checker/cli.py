"""Command-line run, for schedulers (cron, n8n Execute Command, CI).

    python -m checker.cli data/sample_campaigns.csv --out report.html [--offline] [--trap]

Prints a JSON result. Exit code 0 = ready to send, 1 = not ready, 2 = bad input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from checker.config import load_dotenv
from checker.llm_log import totals
from checker.metrics import DataError, load_csv
from checker.pipeline import run
from checker.report import report_html
from checker.sample_data import BRAND
from checker.usage import UsageTracker
from checker.verifier import VERIFIED


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--brand", default=BRAND)
    ap.add_argument("--out", default="report.html")
    ap.add_argument("--offline", action="store_true", help="use the template writer (no LLM)")
    ap.add_argument("--trap", action="store_true", help="inject one wrong number (demo)")
    args = ap.parse_args(argv)
    load_dotenv()

    try:
        df = load_csv(args.csv)
        result = run(df, args.brand, use_llm=not args.offline, trap=args.trap, tracker=UsageTracker())
    except DataError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2

    Path(args.out).write_text(report_html(result), encoding="utf-8")
    v = result.verification
    print(
        json.dumps(
            {
                "ready_to_send": v.ready,
                "score": v.score(),
                "writer": result.writer,
                "notice": result.notice,
                "failed": [
                    {"written": c.raw, "status": c.status, "correct": c.expected, "metric": c.fact_id, "note": c.message}
                    for c in v.checks
                    if c.status != VERIFIED
                ],
                "llm": totals(result.calls),
                "report": str(Path(args.out).resolve()),
            },
            indent=2,
        )
    )
    return 0 if v.ready else 1


if __name__ == "__main__":
    sys.exit(main())
