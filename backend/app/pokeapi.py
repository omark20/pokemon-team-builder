"""PokéAPI over HTTP, called only from the server, with a timeout and retries.

A source has one method, `get(path)`: the parsed JSON, None for a 404, or
UpstreamError for anything else. The scan takes a source as an argument, so tests pass
a fake built from samples/ and this one is used only in production. Retries are done by
`get_with_retry`, which works the same over either source.
"""

import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import httpx

BASE_URL = "https://pokeapi.co/api/v2/"
USER_AGENT = "pokemon-team-builder (server-side daily sync)"
TIMEOUT_SECONDS = 10
RETRY_WAITS = (1, 2, 4)  # seconds before the second, third and fourth attempt


class UpstreamError(Exception):
    """A request that did not give a usable answer. `reason` is a constant for the log."""

    def __init__(self, reason: str, retryable: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class Source(Protocol):
    def get(self, path: str) -> Any: ...


class PokeApiSource:
    """The real PokéAPI. Accepts a path under BASE_URL or a full URL on PokéAPI's host."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def get(self, path: str) -> Any:
        """One attempt: JSON, None for a 404, or UpstreamError."""
        if "://" in path and not path.startswith(BASE_URL):
            raise UpstreamError("foreign_url", retryable=False)
        try:
            response = self.client.get(path)
        except httpx.TimeoutException:
            raise UpstreamError("timeout", retryable=True) from None
        except httpx.TransportError:
            raise UpstreamError("connection", retryable=True) from None
        status = response.status_code
        if status == 404:
            return None
        if status != 200:
            raise UpstreamError(f"http_{status}", retryable=status == 429 or status >= 500)
        try:
            return response.json()
        except ValueError:
            raise UpstreamError("invalid_json", retryable=False) from None


def http_client() -> httpx.Client:
    """The HTTP client for PokéAPI: its base URL, a 10-second timeout, a named User-Agent."""
    return httpx.Client(
        base_url=BASE_URL, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}
    )


def get_with_retry(
    source: Source,
    path: str,
    waits: Sequence[float],
    on_retry: Callable[[str, int, str], None],
) -> Any:
    """`source.get(path)`, retried after each wait on a timeout, connection error, 429 or 5xx.

    `on_retry(path, attempt, reason)` is called before each retry, for the log line.
    """
    for attempt, wait in enumerate(waits, start=1):
        try:
            return source.get(path)
        except UpstreamError as exc:
            if not exc.retryable:
                raise
            on_retry(path, attempt, exc.reason)
            time.sleep(wait)
    return source.get(path)
