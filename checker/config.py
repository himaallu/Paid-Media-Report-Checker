"""Read settings from the environment, a local .env file, or Streamlit secrets.

Order (first wins): real environment variables, then `.env` in the repo root, then
`.streamlit/secrets.toml` / Streamlit Cloud secrets (copied in by app.py).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_FALLBACK_MODELS", "GEMINI_DAILY_LIMIT")


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader (KEY=value per line, # comments). Never overrides real env vars."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def load_secrets(secrets: object) -> None:
    """Copy Streamlit secrets (a mapping) into the environment, without overriding."""
    for key in KEYS:
        try:
            value = secrets[key]  # type: ignore[index]
        except Exception:  # no secrets file, or key not set
            continue
        if value and key not in os.environ:
            os.environ[key] = str(value)


def has_gemini_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))
