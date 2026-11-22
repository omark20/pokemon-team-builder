"""A visitor's teams through the API: what is stored, who may see it, what is refused.

The stored Pokémon are the 14 captured in samples/ (ids 3, 6, 9, 25, 34, 59, 76, 130,
131, 135, 149, 248, 10034, 10264); 7 is not among them.
"""

from typing import Any

import psycopg
import pytest
from fake_pokeapi import FakePokeApi, run_fake_scan
from fastapi.testclient import TestClient

TEAMS = "/api/teams"
SIX_DIFFERENT = [3, 6, 9, 25, 34, 59]


@pytest.fixture
def visitor(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> TestClient:
    """Visitor A, with the captured Pokémon stored."""
    run_fake_scan(conn, source)
    return client


@pytest.fixture
def other_visitor(visitor: TestClient) -> TestClient:
    """Visitor B: the same running app, a separate cookie jar."""
    return TestClient(visitor.app, base_url="https://testserver")


def new_team(client: TestClient, name: str = "Team 1") -> dict[str, Any]:
    response = client.post(TEAMS, json={"name": name})
    assert response.status_code == 201
    team: dict[str, Any] = response.json()
    return team


def set_members(client: TestClient, team_id: int, pokemon_ids: list[Any]) -> Any:
    return client.put(f"{TEAMS}/{team_id}/members", json={"pokemon_ids": pokemon_ids})


def user_count(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT count(*) FROM users").fetchone()
    assert row is not None
    return int(row[0])


def test_create_rename_and_delete_leave_other_teams_alone(visitor: TestClient) -> None:
    first, second = new_team(visitor, "  First  "), new_team(visitor, "Second")
    assert first == {"id": first["id"], "name": "First", "pokemon_ids": []}
    renamed = visitor.patch(f"{TEAMS}/{second['id']}", json={"name": "Renamed"})
    assert renamed.json()["name"] == "Renamed"
    assert visitor.delete(f"{TEAMS}/{first['id']}").status_code == 204
    assert visitor.get(TEAMS).json() == [{"id": second["id"], "name": "Renamed", "pokemon_ids": []}]


@pytest.mark.parametrize(
    "pokemon_ids",
    [[], [25], SIX_DIFFERENT, SIX_DIFFERENT[::-1], [6, 6, 25], [6, 25, 6], [6] * 6],
    ids=["empty", "one", "six", "six-reversed", "repeat-adjacent", "repeat-apart", "six-of-one"],
)
def test_members_come_back_exactly_as_sent(visitor: TestClient, pokemon_ids: list[int]) -> None:
    team = new_team(visitor)
    assert set_members(visitor, team["id"], pokemon_ids).json()["pokemon_ids"] == pokemon_ids
    assert visitor.get(TEAMS).json()[0]["pokemon_ids"] == pokemon_ids


def test_a_shorter_replace_leaves_positions_1_to_n(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team = new_team(visitor)
    set_members(visitor, team["id"], SIX_DIFFERENT)
    set_members(visitor, team["id"], [25, 6])
    rows = conn.execute("SELECT position, pokemon_id FROM team_members ORDER BY position")
    assert rows.fetchall() == [(1, 25), (2, 6)]


@pytest.mark.parametrize(
    "pokemon_ids",
    [[*SIX_DIFFERENT, 76], [6] * 7, [6, 7]],
    ids=["seven-different", "seven-repeating", "unknown-id"],
)
def test_refused_member_lists_are_422_and_change_nothing(
    visitor: TestClient, pokemon_ids: list[int]
) -> None:
    team = new_team(visitor)
    set_members(visitor, team["id"], [25])
    assert set_members(visitor, team["id"], pokemon_ids).status_code == 422
    assert visitor.get(TEAMS).json()[0]["pokemon_ids"] == [25]


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("PATCH", "", {"name": "Mine now"}),
        ("PUT", "/members", {"pokemon_ids": [6]}),
        ("DELETE", "", None),
    ],
)
def test_another_visitors_team_is_404_for_every_verb(
    visitor: TestClient, other_visitor: TestClient, method: str, suffix: str, body: object
) -> None:
    team = new_team(visitor)
    new_team(other_visitor)  # B is a known visitor, not merely one without a cookie
    response = other_visitor.request(method, f"{TEAMS}/{team['id']}{suffix}", json=body)
    assert response.status_code == 404
    assert visitor.get(TEAMS).json() == [team]


def test_a_user_id_in_the_body_is_refused_and_in_the_query_ignored(
    visitor: TestClient, other_visitor: TestClient
) -> None:
    team = new_team(visitor)
    body = {"name": "Taken", "user_id": 1}
    assert other_visitor.post(TEAMS, json=body).status_code == 422
    assert other_visitor.get(TEAMS, params={"user_id": 1}).json() == []
    assert visitor.get(TEAMS).json() == [team]


def test_the_cookie_is_httponly_secure_and_samesite_lax(visitor: TestClient) -> None:
    response = visitor.post(TEAMS, json={"name": "Team 1"})
    flags = {part.strip().lower() for part in response.headers["set-cookie"].split(";")}
    assert {"httponly", "secure", "samesite=lax", "path=/", "max-age=31536000"} <= flags


def test_reading_without_a_cookie_creates_no_visitor(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    assert visitor.get(TEAMS).json() == []
    assert user_count(conn) == 0


def test_a_made_up_cookie_is_treated_as_none(visitor: TestClient, conn: psycopg.Connection) -> None:
    new_team(visitor)
    visitor.cookies.clear()
    made_up = {"Cookie": "uid=not-a-cookie-this-server-issued"}
    assert visitor.get(TEAMS, headers=made_up).json() == []
    assert visitor.patch(f"{TEAMS}/1", json={"name": "x"}, headers=made_up).status_code == 404


def test_the_21st_team_is_409(visitor: TestClient) -> None:
    for number in range(20):
        new_team(visitor, f"Team {number}")
    assert visitor.post(TEAMS, json={"name": "One too many"}).status_code == 409


@pytest.mark.parametrize(
    ("name", "status"), [("x" * 50, 201), ("x" * 51, 422), ("   ", 422), ("", 422)]
)
def test_names_are_1_to_50_characters_after_trimming(
    visitor: TestClient, name: str, status: int
) -> None:
    assert visitor.post(TEAMS, json={"name": name}).status_code == status


@pytest.mark.parametrize("name", ["<img src=x onerror=alert(1)>", "'; DROP TABLE teams;--"])
def test_hostile_names_are_stored_and_returned_verbatim(
    visitor: TestClient, conn: psycopg.Connection, name: str
) -> None:
    team = new_team(visitor, name)
    assert visitor.get(TEAMS).json() == [team]
    assert team["name"] == name
    assert conn.execute("SELECT to_regclass('teams')").fetchone() == ("teams",)


@pytest.mark.parametrize(
    ("method", "path", "content"),
    [
        ("POST", TEAMS, b'{"name": '),
        ("POST", TEAMS, b'{"name": 5}'),
        ("PUT", f"{TEAMS}/1/members", b'{"pokemon_ids": ["6"]}'),
        ("PUT", f"{TEAMS}/1/members", b'{"pokemon_ids": 6}'),
        ("PATCH", f"{TEAMS}/12345678901234567890", b'{"name": "x"}'),
        ("DELETE", f"{TEAMS}/0", None),
    ],
    ids=["malformed-json", "name-not-text", "id-as-text", "list-not-array", "20-digit-id", "id-0"],
)
def test_malformed_requests_are_4xx_never_500(
    visitor: TestClient, method: str, path: str, content: bytes | None
) -> None:
    new_team(visitor)
    headers = {"Content-Type": "application/json"}
    response = visitor.request(method, path, content=content, headers=headers)
    assert 400 <= response.status_code < 500
