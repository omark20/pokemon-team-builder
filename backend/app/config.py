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
    """Read the settings. An unset or empty token keeps its endpoints closed."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return Settings(
        database_url=database_url,
        scan_token=os.environ.get("SCAN_TOKEN") or None,
        admin_token=os.environ.get("ADMIN_TOKEN") or None,
    )
