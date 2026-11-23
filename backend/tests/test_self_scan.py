"""The app's own scan start: the rule for when one is due, one look, and the loop.

The rule is checked at a fixed time; looks are given their time and run the fake
source; the loop is given a sleep that returns at once. Nothing here really waits.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from conftest import SCAN_TOKEN
from fake_pokeapi import POKEMON_LIST, FakePokeApi, run_fake_scan
from fastapi.testclient import TestClient

from app import scan, self_scan
from app.config import Settings
from app.main import create_app
from app.pokeapi import UpstreamError
from app.scan import run_scan, utc_now
from app.self_scan import Facts, decide

NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)
HOUR, MINUTE = timedelta(hours=1), timedelta(minutes=1)


@pytest.mark.parametrize(
    ("facts", "decision"),
    [
        (Facts(None, None, False), "due"),
        (Facts(NOW - 7 * HOUR - MINUTE, NOW - 7 * HOUR - MINUTE, False), "due"),
        (Facts(NOW - 7 * HOUR + MINUTE, NOW - 7 * HOUR + MINUTE, False), "not_due"),
        (Facts(NOW - 8 * HOUR, NOW - 30 * MINUTE, False), "not_due"),
        (Facts(NOW - 8 * HOUR, NOW - 61 * MINUTE, False), "due"),
        (Facts(NOW - 8 * HOUR, NOW - 8 * HOUR, True), "paused_for_demo"),
        (Facts(NOW - 2 * HOUR, NOW - 2 * HOUR, False, True), "due"),
        (Facts(NOW - 30 * MINUTE, NOW - 30 * MINUTE, False, True), "not_due"),
        (Facts(NOW - 2 * HOUR, NOW - 2 * HOUR, True, True), "paused_for_demo"),
    ],
    ids=[
        "never-scanned",
        "7h01",
        "6h59",
        "failed-30-minutes-ago",
        "failed-61-minutes-ago",
        "demo-active",
        "no-duel-data-after-a-recent-scan",
        "no-duel-data-tried-30-minutes-ago",
        "no-duel-data-in-a-demo",
    ],
)
def test_a_scan_is_due_after_7_hours_or_without_duel_data_hourly_at_most_never_in_a_demo(
    facts: Facts, decision: str
) -> None:
    assert decide(NOW, facts) == decision


def runs(conn: psycopg.Connection) -> list[tuple[str, str, str | None]]:
    rows = conn.execute("SELECT status, scope, started_by FROM scan_runs ORDER BY id")
    return [(status, scope, started_by) for status, scope, started_by in rows]


def look(client: TestClient, conn: psycopg.Connection, source: FakePokeApi, at: datetime) -> object:
    """One look at `at`, running a due scan against the fake source with no retry waits."""
    pool = client.app.state.pool  # type: ignore[attr-defined]
    return self_scan.look(
        pool, at, lambda run_id: run_scan(conn, source, run_id, retry_waits=(0, 0, 0))
    )


def test_a_due_look_runs_a_scan_started_by_the_app(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    assert look(client, conn, source, utc_now()) is not None
    assert runs(conn) == [("ok", "full", "app")]


def test_a_look_when_not_due_starts_nothing(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source)  # a finished full scan, which stores the duel data too
    assert look(client, conn, source, utc_now() + HOUR) is None
    assert len(runs(conn)) == 1


def test_a_look_while_a_run_is_in_progress_starts_nothing_and_raises_nothing(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    conn.execute("INSERT INTO scan_runs (status, scope) VALUES ('running', 'subset')")
    assert look(client, conn, source, utc_now()) is None
    assert runs(conn) == [("running", "subset", None)]


def test_a_failing_source_is_tried_again_after_an_hour_not_before(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    source.answers[POKEMON_LIST] = UpstreamError("http_503", retryable=True)
    first = utc_now()
    assert look(client, conn, source, first) is not None
    assert look(client, conn, source, first + 10 * MINUTE) is None
    assert look(client, conn, source, first + 61 * MINUTE) is not None
    assert runs(conn) == [("failed", "full", "app")] * 2


def test_a_run_started_by_the_endpoint_is_marked_api(
    client: TestClient, conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scan, "scan_with_pokeapi", lambda *_: "ok")  # no live PokéAPI
    response = client.post("/api/admin/scan", headers={"Authorization": f"Bearer {SCAN_TOKEN}"})
    assert response.status_code == 202
    [(_, scope, started_by)] = runs(conn)
    assert (scope, started_by) == ("full", "api")


def test_a_look_that_raises_does_not_end_the_loop() -> None:
    looks: list[int] = []

    def failing_look() -> None:
        looks.append(len(looks))
        raise RuntimeError("database unreachable")

    async def sleep(_: float) -> None:
        if len(looks) == 3:
            raise asyncio.CancelledError  # stop the loop once it has carried on twice

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(self_scan.keep_scanned(failing_look, sleep))
    assert looks == [0, 1, 2]


def test_the_running_app_looks_by_itself(
    settings: Settings, conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(self_scan, "LOOK_EVERY_SECONDS", 0)
    monkeypatch.setattr(scan, "scan_with_pokeapi", lambda *_: "ok")  # no live PokéAPI
    with TestClient(create_app(settings), base_url="https://testserver"):
        deadline = time.monotonic() + 5
        while not runs(conn) and time.monotonic() < deadline:
            time.sleep(0.05)
    assert runs(conn) == [("running", "full", "app")]
