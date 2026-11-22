"""Settings read from the environment: the database address and the two admin tokens.

Values come only from environment variables (the host's settings in production, the
git-ignored .env locally), so no secret is written in the code. The two tokens are
separate secrets: SCAN_TOKEN may only start a scan, ADMIN_TOKEN runs the demo controls.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Everything the app reads from outside. Secrets are left out of the repr."""

    database_url: str = field(repr=False)
    scan_token: str | None = field(repr=False)
    admin_token: str | None = field(repr=False)


def load_settings() -> Settings:
    """Read the settings. An unset or blank token keeps its endpoints closed.

    The two tokens must differ: the scheduler holds SCAN_TOKEN, and if it equalled
    ADMIN_TOKEN a leak from the scheduler could change what the site shows.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    scan_token, admin_token = _token("SCAN_TOKEN"), _token("ADMIN_TOKEN")
    if scan_token is not None and scan_token == admin_token:
        raise RuntimeError("SCAN_TOKEN and ADMIN_TOKEN must be different values")
    return Settings(database_url=database_url, scan_token=scan_token, admin_token=admin_token)


def _token(name: str) -> str | None:
    """The token without surrounding whitespace, or None if it is unset or blank."""
    return os.environ.get(name, "").strip() or None
