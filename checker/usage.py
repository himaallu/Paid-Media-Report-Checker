"""Count Gemini requests per model per day, to show how many free-tier calls are left.

Google doesn't report the remaining daily quota through the API, so the app counts
the requests it makes itself. The free-tier daily quota resets at midnight Pacific
time, so the count does too. Limits are per model (default 20/day, set with
GEMINI_DAILY_LIMIT). Calls made with the same key outside this app aren't counted.

A 429 that says the daily quota is used up marks that model as exhausted for the
day, so the counter corrects itself, and the writer skips that model until midnight.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from checker.config import ROOT

DEFAULT_DAILY_LIMIT = 20
DEFAULT_FILE = ROOT / ".usage" / "gemini_calls.json"


def pacific_today() -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Los_Angeles")).date()
    except Exception:  # no tz database (e.g. some Windows installs): approximate with UTC-8
        return datetime.now(timezone(timedelta(hours=-8))).date()


def daily_limit() -> int:
    try:
        return max(1, int(os.environ.get("GEMINI_DAILY_LIMIT", DEFAULT_DAILY_LIMIT)))
    except ValueError:
        return DEFAULT_DAILY_LIMIT


class UsageTracker:
    def __init__(self, path: Path | None = None, today: date | None = None):
        self.path = Path(path or os.environ.get("GEMINI_USAGE_FILE", DEFAULT_FILE))
        self._today = today

    @property
    def today(self) -> str:
        return (self._today or pacific_today()).isoformat()

    def _load(self) -> dict[str, dict[str, int]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if data.get("date") != self.today:  # a new day: start again
            return {}
        return data.get("models", {})

    def _save(self, models: dict[str, dict[str, int]]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"date": self.today, "models": models}, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass  # read-only disk: the counter just won't persist

    def record(self, model: str) -> None:
        """One request that reached Gemini and counts against the daily quota."""
        models = self._load()
        entry = models.setdefault(model, {"used": 0})
        entry["used"] = entry.get("used", 0) + 1
        self._save(models)

    def mark_exhausted(self, model: str) -> None:
        models = self._load()
        models.setdefault(model, {"used": 0})["exhausted"] = 1
        self._save(models)

    def used(self, model: str) -> int:
        return self._load().get(model, {}).get("used", 0)

    def remaining(self, model: str) -> int:
        entry = self._load().get(model, {})
        if entry.get("exhausted"):
            return 0
        return max(0, daily_limit() - entry.get("used", 0))

    def snapshot(self, models: list[str]) -> list[dict[str, object]]:
        limit = daily_limit()
        return [{"model": m, "used": self.used(m), "remaining": self.remaining(m), "limit": limit} for m in models]
