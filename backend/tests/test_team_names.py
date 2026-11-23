"""Team names are unique per owner, ignoring capitals: the naming rule, the start-up
step that repairs stored clashes and creates the index, the 409s, the races the index
decides, and the sign-in merge renaming an incoming team."""

import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app import team_names
from app.config import Settings
from app.main import create_app
from app.routes.teams import TOO_MANY
from app.team_names import TAKEN, free_name

TEAMS = "/api/teams"
FIFTY = "x" * 50
PASSWORD = "a long enough password"


@pytest.mark.parametrize(
    ("name", "taken", "expected"),
    [
        ("Team 2", set(), "Team 2"),
        ("Team 2", {"team 2"}, "Team 2 (2)"),
        ("Team 2", {"team 2", "team 2 (2)"}, "Team 2 (3)"),
        ("TEAM 2", {"team 2"}, "TEAM 2 (2)"),
        (FIFTY, {FIFTY}, "x" * 46 + " (2)"),
        ("x" * 45 + " abcd", {"x" * 45 + " abcd"}, "x" * 45 + " (2)"),  # no space before "("
    ],
    ids=["free", "taken", "two-taken", "capitals", "fifty", "cut-at-a-space"],
)
def test_a_name_that_is_taken_gets_the_first_free_number(
    name: str, taken: set[str], expected: str
) -> None:
    assert free_name(name, taken, str.lower) == expected
    assert len(expected) <= team_names.MAX_NAME


def new_visitor(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "INSERT INTO users (token_hash) VALUES (%s) RETURNING id", (os.urandom(32),)
    ).fetchone()
    assert row is not None
    return int(row[0])


def seed_clashes(conn: psycopg.Connection) -> int:
    """Drop the index and store clashes as if made before it existed; the owner's ID."""
    conn.execute(f"DROP INDEX {team_names.INDEX}")
    owner, other = new_visitor(conn), new_visitor(conn)
    names = ["Team 2", "Team 2", "Alpha", "ALPHA", "Beta", "Beta (2)", "Beta", FIFTY, FIFTY]
    start = datetime(2026, 11, 1, tzinfo=UTC)
    for minutes, name in enumerate(names):
        conn.execute(
            "INSERT INTO teams (user_id, name, created_at) VALUES (%s, %s, %s)",
            (owner, name, start + timedelta(minutes=minutes)),
        )
    conn.execute("INSERT INTO teams (user_id, name) VALUES (%s, 'Team 2')", (other,))
    return owner


def stored_names(conn: psycopg.Connection, owner: int) -> list[str]:
    rows = conn.execute("SELECT name FROM teams WHERE user_id = %s ORDER BY created_at", (owner,))
    return [name for (name,) in rows]


def test_start_up_renames_stored_clashes_oldest_kept_and_creates_the_index_once(
    conn: psycopg.Connection, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    owner = seed_clashes(conn)
    expected = ["Team 2", "Team 2 (2)", "Alpha", "ALPHA (2)", "Beta", "Beta (2)", "Beta (3)"]
    expected += [FIFTY, "x" * 46 + " (2)"]
    for _ in range(2):  # the second start finds the index and changes nothing
        with caplog.at_level(logging.INFO), TestClient(create_app(settings)):
            pass
    assert stored_names(conn, owner) == expected
    lines = [line for line in caplog.messages if line.startswith("team_names_made_unique")]
    assert lines == ["team_names_made_unique renamed=4"]
    index = conn.execute("SELECT to_regclass(%s)", (team_names.INDEX,)).fetchone()
    assert index == (team_names.INDEX,)


def test_a_new_database_starts_with_the_index(conn: psycopg.Connection) -> None:
    index = conn.execute("SELECT to_regclass(%s)", (team_names.INDEX,)).fetchone()
    assert index == (team_names.INDEX,)


def test_if_the_start_up_step_fails_the_app_does_not_start_and_logs_no_message(
    conn: psycopg.Connection,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def failing(_: psycopg.Connection) -> None:
        raise ValueError("Key (user_id, lower(name))=(1, secret team) already exists")

    monkeypatch.setattr(team_names, "make_names_unique", failing)
    with pytest.raises(RuntimeError), TestClient(create_app(settings)):
        pass
    assert any(line.startswith("team_names_failed") for line in caplog.messages)
    assert not any("secret team" in line for line in caplog.messages)


def same_visitor(client: TestClient) -> TestClient:
    """A second connection for the same visitor: the same app and cookie."""
    other = TestClient(client.app, base_url="https://testserver")
    other.cookies.set("uid", client.cookies["uid"])
    return other


def at_once(clients: list[TestClient], send: Callable[[TestClient], Response]) -> list[int]:
    """Send one request from each client at the same moment; the status codes, sorted."""
    start = threading.Barrier(len(clients))

    def go(client: TestClient) -> int:
        start.wait()
        return send(client).status_code

    with ThreadPoolExecutor(len(clients)) as pool:
        return sorted(pool.map(go, clients))


def test_two_creates_with_one_name_at_once_give_one_team_and_one_409(
    client: TestClient, conn: psycopg.Connection
) -> None:
    client.post(TEAMS, json={"name": "First"})  # the visitor and their cookie
    codes = at_once([client, same_visitor(client)], lambda c: c.post(TEAMS, json={"name": "Same"}))
    assert codes == [201, 409]
    stored = conn.execute("SELECT count(*) FROM teams WHERE lower(name) = 'same'").fetchone()
    assert stored == (1,)


def test_two_renames_to_one_name_at_once_give_one_and_one_409(
    client: TestClient, conn: psycopg.Connection
) -> None:
    ids = iter([client.post(TEAMS, json={"name": name}).json()["id"] for name in ("A", "B")])
    clients = [client, same_visitor(client)]
    lock = threading.Lock()

    def rename(c: TestClient) -> Response:
        with lock:
            team_id = next(ids)
        return c.patch(f"{TEAMS}/{team_id}", json={"name": "Same"})

    assert at_once(clients, rename) == [200, 409]
    stored = conn.execute("SELECT count(*) FROM teams WHERE name = 'Same'").fetchone()
    assert stored == (1,)


def test_the_two_409s_on_create_are_told_apart_by_their_text(client: TestClient) -> None:
    assert client.post(TEAMS, json={"name": "Team 1"}).status_code == 201
    taken = client.post(TEAMS, json={"name": "TEAM 1"})
    assert (taken.status_code, taken.json()["detail"]) == (409, TAKEN)
    for number in range(2, 21):
        client.post(TEAMS, json={"name": f"Team {number}"})
    full = client.post(TEAMS, json={"name": "Team 21"})
    assert (full.status_code, full.json()["detail"]) == (409, TOO_MANY)


def test_a_rename_to_a_taken_name_is_409_and_to_its_own_name_in_capitals_is_not(
    client: TestClient,
) -> None:
    team_id = client.post(TEAMS, json={"name": "Team 2"}).json()["id"]
    other_id = client.post(TEAMS, json={"name": "Team 3"}).json()["id"]
    refused = client.patch(f"{TEAMS}/{other_id}", json={"name": "team 2"})
    assert (refused.status_code, refused.json()["detail"]) == (409, TAKEN)
    renamed = client.patch(f"{TEAMS}/{team_id}", json={"name": "TEAM 2"})
    assert (renamed.status_code, renamed.json()["name"]) == (200, "TEAM 2")


def test_a_browser_team_whose_name_the_account_has_is_renamed_on_sign_in(
    client: TestClient,
) -> None:
    client.post("/api/account", json={"username": "Misty", "password": PASSWORD})
    for name in ("Team 2", "Team 2 (2)"):
        assert client.post(TEAMS, json={"name": name}).status_code == 201
    laptop = TestClient(client.app, base_url="https://testserver")
    laptop.post(TEAMS, json={"name": "Team 2"})
    signed_in = laptop.post("/api/session", json={"username": "Misty", "password": PASSWORD})
    assert (signed_in.json()["teams_added"], signed_in.json()["teams_renamed"]) == (1, 1)
    names = [team["name"] for team in laptop.get(TEAMS).json()]
    assert names == ["Team 2", "Team 2 (2)", "Team 2 (3)"]
