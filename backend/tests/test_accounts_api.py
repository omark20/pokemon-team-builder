"""Optional accounts through the API: sign-up, sign-in and its merge, sessions, limits.

Each `browser` is a separate cookie jar on the same running app. Teams are made empty
unless a test needs a Pokémon in one; the stored Pokémon are the captured samples.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fake_pokeapi import FakePokeApi, run_fake_scan
from fastapi.testclient import TestClient
from httpx import Response
from starlette.requests import Request
from test_alerts_api import add_change, team_with

from app import account_store, accounts, auth
from app.routes import sessions

PASSWORD = "correct horse battery"
TEAMS = "/api/teams"
ANONYMOUS = "SELECT count(*) FROM users WHERE token_hash IS NOT NULL"


def browser(client: TestClient) -> TestClient:
    """Another browser: the same running app, its own cookie jar."""
    return TestClient(client.app, base_url="https://testserver")


def with_cookie(client: TestClient, value: str) -> TestClient:
    """A browser holding this cookie value and nothing else."""
    other = browser(client)
    other.headers["Cookie"] = f"uid={value}"
    return other


def sign_up(client: TestClient, name: str = "Misty", password: str = PASSWORD) -> Response:
    return client.post("/api/account", json={"username": name, "password": password})


def sign_in(client: TestClient, name: str = "Misty", password: str = PASSWORD) -> Response:
    return client.post("/api/session", json={"username": name, "password": password})


def make_teams(client: TestClient, prefix: str, count: int) -> None:
    for number in range(1, count + 1):
        assert client.post(TEAMS, json={"name": f"{prefix}{number}"}).status_code == 201


def team_names(client: TestClient) -> list[str]:
    return [team["name"] for team in client.get(TEAMS).json()]


def count(conn: psycopg.Connection, query: str, *params: Any) -> int:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return int(row[0])


def from_address(number: int) -> dict[str, str]:
    """Headers that make a request count under its own address, as the edge would set."""
    return {"CF-Connecting-IP": f"203.0.113.{number}"}


# Sign-up


def test_an_anonymous_visitor_keeps_their_teams_and_gets_a_new_cookie(
    client: TestClient,
) -> None:
    make_teams(client, "t", 2)
    old_cookie = client.cookies["uid"]
    assert sign_up(client).status_code == 201
    assert client.cookies["uid"] != old_cookie
    assert team_names(client) == ["t1", "t2"]
    assert client.get("/api/session").json() == {"username": "Misty"}
    assert team_names(with_cookie(client, old_cookie)) == []


def test_a_visitor_with_no_cookie_can_sign_up(client: TestClient) -> None:
    response = sign_up(client)
    assert (response.status_code, response.json()) == (201, {"username": "Misty"})
    assert client.get("/api/session").json() == {"username": "Misty"}


def test_a_taken_name_in_any_capitals_is_409(client: TestClient) -> None:
    sign_up(client)
    response = sign_up(browser(client), "mISTY")
    assert (response.status_code, response.json()) == (409, {"detail": "That username is taken."})


def test_signing_up_while_signed_in_is_409(client: TestClient) -> None:
    sign_up(client)
    response = sign_up(client, "Brock")
    assert (response.status_code, response.json()) == (409, {"detail": account_store.SIGNED_IN})


@pytest.mark.parametrize("anonymous", [True, False], ids=["anonymous-record", "no-cookie"])
def test_a_name_taken_between_the_check_and_the_write_is_still_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, anonymous: bool
) -> None:
    sign_up(client)
    late = browser(client)
    if anonymous:
        make_teams(late, "t", 1)
    monkeypatch.setattr(account_store, "find_account", lambda *_: None)  # the check misses it
    response = sign_up(late, "misty")
    assert (response.status_code, response.json()) == (409, {"detail": "That username is taken."})


@pytest.mark.parametrize(
    ("name", "password", "sentence"),
    [
        ("ab", PASSWORD, accounts.username_problem("ab")),
        ("Misty", "password1", "That password is too common. Choose another."),
    ],
    ids=["username", "password"],
)
def test_a_broken_rule_is_422_with_its_sentence_and_makes_nothing(
    client: TestClient, conn: psycopg.Connection, name: str, password: str, sentence: str
) -> None:
    response = sign_up(client, name, password)
    assert (response.status_code, response.json()) == (422, {"detail": sentence})
    assert count(conn, "SELECT count(*) FROM users") == 0


# Sign-in


def test_the_right_password_gives_a_new_cookie_and_the_accounts_teams(
    client: TestClient,
) -> None:
    sign_up(client)
    make_teams(client, "a", 2)
    laptop = browser(client)
    response = sign_in(laptop, "misty")
    assert response.json() == {"username": "Misty", "teams_added": 0, "teams_not_added": 0}
    assert laptop.cookies["uid"] != client.cookies["uid"]
    assert team_names(laptop) == ["a1", "a2"]


class SpyHasher:
    """Records the stored hash every verify is given, then does the real verify."""

    def __init__(self) -> None:
        self.real = accounts.HASHER
        self.verified: list[str] = []

    def verify(self, stored: str, password: str) -> bool:
        self.verified.append(stored)
        return self.real.verify(stored, password)


def test_an_unknown_name_and_a_wrong_password_get_the_same_answer_after_a_verify(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_up(client)
    spy = SpyHasher()
    monkeypatch.setattr(accounts, "HASHER", spy)
    stranger = browser(client)
    unknown, wrong = sign_in(stranger, "Brock"), sign_in(stranger, "Misty", "not the password")
    assert (unknown.status_code, unknown.json()) == (401, {"detail": "Wrong username or password."})
    assert (wrong.status_code, wrong.json()) == (unknown.status_code, unknown.json())
    assert spy.verified[0] == accounts.DUMMY_HASH
    assert spy.verified[1] != accounts.DUMMY_HASH
    assert "uid" not in stranger.cookies


def test_a_signed_in_visitor_cannot_reach_another_accounts_team(client: TestClient) -> None:
    sign_up(client)
    team_id = client.post(TEAMS, json={"name": "mine"}).json()["id"]
    other = browser(client)
    sign_up(other, "Brock")
    assert other.get(f"{TEAMS}/{team_id}/counter").status_code == 404
    assert other.patch(f"{TEAMS}/{team_id}", json={"name": "x"}).status_code == 404


def test_an_account_deleted_after_its_password_was_checked_is_401_not_500(
    client: TestClient, conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_up(client)
    real_matches = accounts.password_matches

    def matches_then_deleted(stored: str | None, password: str) -> bool:
        matched = real_matches(stored, password)
        conn.execute("DELETE FROM users WHERE username_key = 'misty'")  # another browser's delete
        return matched

    monkeypatch.setattr(accounts, "password_matches", matches_then_deleted)
    laptop = browser(client)
    response = sign_in(laptop)
    assert (response.status_code, response.json()) == (
        401,
        {"detail": "Wrong username or password."},
    )
    assert "uid" not in laptop.cookies


# Sessions


def test_signing_out_of_one_browser_leaves_the_other_signed_in(client: TestClient) -> None:
    sign_up(client)
    make_teams(client, "a", 1)
    laptop = browser(client)
    sign_in(laptop)
    phone_cookie = client.cookies["uid"]
    response = client.delete("/api/session")
    assert response.status_code == 204
    assert "uid" not in client.cookies
    assert team_names(laptop) == ["a1"]
    used = with_cookie(client, phone_cookie)
    assert (team_names(used), used.get("/api/session").json()) == ([], {"username": None})


@pytest.mark.parametrize(
    ("age", "signed_in"),
    [(timedelta(days=30) - timedelta(seconds=1), True), (timedelta(days=30, seconds=1), False)],
    ids=["30-days-less-1s", "30-days-and-1s"],
)
def test_a_session_lasts_30_days(
    client: TestClient, conn: psycopg.Connection, age: timedelta, signed_in: bool
) -> None:
    sign_up(client)
    started = datetime(2026, 11, 22, 12, tzinfo=UTC)
    conn.execute("UPDATE sessions SET created_at = %s", (started,))
    cookie = f"uid={client.cookies['uid']}".encode()
    request = Request({"type": "http", "headers": [(b"cookie", cookie)]})
    identity = auth.identify(request, conn, started + age)
    assert (identity is not None and identity.signed_in) == signed_in


def test_the_eleventh_session_removes_the_oldest(
    client: TestClient, conn: psycopg.Connection
) -> None:
    sign_up(client)
    browsers = [browser(client) for _ in range(10)]
    for other in browsers:
        assert sign_in(other).status_code == 200
    assert count(conn, "SELECT count(*) FROM sessions") == 10
    assert client.get("/api/session").json() == {"username": None}
    assert all(other.get("/api/session").json() == {"username": "Misty"} for other in browsers)


def test_an_anonymous_visitor_who_signs_out_keeps_their_teams(client: TestClient) -> None:
    make_teams(client, "t", 1)
    assert client.get("/api/session").json() == {"username": None}
    assert client.delete("/api/session").status_code == 204
    assert team_names(client) == ["t1"]


def test_who_am_i_without_a_cookie_touches_no_database(
    client: TestClient, connect_calls: list[object]
) -> None:
    assert client.get("/api/session").json() == {"username": None}
    assert client.delete("/api/session").status_code == 204
    assert connect_calls == []


# The merge


@pytest.mark.parametrize(
    ("brought", "held", "kept"),
    [(3, 5, ["b1", "b2", "b3"]), (4, 18, ["b1", "b2"]), (0, 5, [])],
    ids=["3-into-5", "4-into-18", "no-teams"],
)
def test_a_browsers_teams_join_the_account_oldest_first_up_to_20(
    client: TestClient, conn: psycopg.Connection, brought: int, held: int, kept: list[str]
) -> None:
    sign_up(client)
    make_teams(client, "a", held)
    laptop = browser(client)
    make_teams(laptop, "b", brought)
    response = sign_in(laptop)
    added = {"teams_added": len(kept), "teams_not_added": brought - len(kept)}
    assert response.json() == {"username": "Misty", **added}
    assert team_names(laptop) == [f"a{n}" for n in range(1, held + 1)] + kept
    assert count(conn, "SELECT count(*) FROM teams WHERE name LIKE 'b%%'") == len(kept)
    assert count(conn, ANONYMOUS) == 0


def test_a_browser_signed_in_to_another_account_brings_nothing(
    client: TestClient, conn: psycopg.Connection
) -> None:
    sign_up(client)
    laptop = browser(client)
    sign_up(laptop, "Brock")
    make_teams(laptop, "brock", 2)
    assert sign_in(laptop).json() == {"username": "Misty", "teams_added": 0, "teams_not_added": 0}
    assert team_names(laptop) == []
    assert count(conn, "SELECT count(*) FROM sessions") == 2  # Brock's session went


def test_a_dismissal_made_in_the_browser_holds_after_the_merge(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source)
    sign_up(client)
    laptop = browser(client)
    team_with(laptop, [6])
    change_id = add_change(conn)
    assert laptop.post(f"/api/alerts/{change_id}/dismiss").status_code == 204
    sign_in(laptop)
    assert team_names(client) == ["Team"]
    assert client.get("/api/alerts").json() == []


# What is never sent back, and what is refused


@pytest.mark.parametrize("path", ["/api/account", "/api/session"])
@pytest.mark.parametrize(
    "body",
    [
        f'{{"username": "Misty", "password": "{PASSWORD}", "extra": 1}}',
        f'{{"username": 5, "password": "{PASSWORD}"}}',
        f'{{"username": "{"x" * 65}", "password": "{PASSWORD}"}}',
        f'{{"password": "{PASSWORD}"}}',
        f'{{"username": "Misty", "password": ["{PASSWORD}"]}}',
        f'{{"username": "Misty", "password": "{PASSWORD}"',
    ],
    ids=["unknown-field", "number-name", "long-name", "no-name", "list", "cut-short"],
)
def test_a_malformed_body_is_422_without_its_password(
    client: TestClient, path: str, body: str
) -> None:
    response = client.post(path, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert PASSWORD not in response.text


def test_a_sign_in_sent_as_a_form_from_another_site_is_refused(
    client: TestClient, conn: psycopg.Connection
) -> None:
    sign_up(client)
    client.cookies.clear()
    form = {"username": "Misty", "password": PASSWORD}
    response = client.post("/api/session", data=form, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert count(conn, "SELECT count(*) FROM sessions") == 1


def test_a_record_is_never_both_anonymous_and_an_account(
    client: TestClient, conn: psycopg.Connection
) -> None:
    make_teams(client, "t", 1)
    sign_up(client)
    laptop = browser(client)
    make_teams(laptop, "b", 1)
    sign_in(laptop)
    sign_up(browser(client), "Brock")
    laptop.delete("/api/session")
    make_teams(laptop, "c", 1)
    mixed = """
        SELECT count(*) FROM users
        WHERE (token_hash IS NULL) = (username IS NULL)
           OR (username IS NULL) <> (username_key IS NULL)
           OR (username IS NULL) <> (password_hash IS NULL)
    """
    assert count(conn, "SELECT count(*) FROM users") == 3  # Misty, Brock, one anonymous
    assert count(conn, mixed) == 0


# Limits


PAIR = [("Misty", 1)] * 10  # one username from one address
ONE_ADDRESS = [(f"name{n}", 1) for n in range(20)]  # one address, several names
# One username in other capitals from ten addresses, ten each: within both counts above.
SPREAD = [("MiStY" if n % 2 else "misty", 1 + n // 10) for n in range(100)]


@pytest.mark.parametrize(
    ("allowed", "refused", "owner_elsewhere"),
    [
        (PAIR, ("misty", 1), 200),
        ([("Brock", 1)] * 10, ("brock", 1), 200),
        (ONE_ADDRESS, ("name20", 1), 200),
        (SPREAD, ("MISTY", 11), 429),
    ],
    ids=["one-name-one-address", "unknown-name-one-address", "one-address", "one-name-everywhere"],
)
def test_sign_in_attempts_are_counted_per_name_and_address_per_address_and_per_name(
    client: TestClient,
    allowed: list[tuple[str, int]],
    refused: tuple[str, int],
    owner_elsewhere: int,
) -> None:
    sign_up(browser(client))

    def attempt(name: str, address: int, password: str = "a wrong guess") -> int:
        body = {"username": name, "password": password}
        response = client.post("/api/session", json=body, headers=from_address(address))
        return response.status_code

    answers = [attempt(name, address) for name, address in allowed] + [attempt(*refused)]
    assert answers == [401] * len(allowed) + [429]
    assert attempt("Misty", 99, PASSWORD) == owner_elsewhere


def test_the_sixth_creation_attempt_from_one_address_is_429_taken_names_included(
    client: TestClient,
) -> None:
    answers = []
    for _ in range(6):
        client.cookies.clear()
        answers.append(sign_up(client).status_code)
    assert answers == [201, 409, 409, 409, 409, 429]


def test_the_sixty_first_creation_attempt_from_all_addresses_is_429(client: TestClient) -> None:
    answers = [
        client.post(
            "/api/account",
            json={"username": "Misty", "password": "short"},
            headers=from_address(n),
        ).status_code
        for n in range(61)
    ]
    assert answers == [422] * 60 + [429]


def test_with_two_hashes_held_a_third_sign_in_is_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sessions, "HASH_WAIT_SECONDS", 0.1)
    places = client.app.state.hash_places  # type: ignore[attr-defined]
    for _ in range(sessions.HASH_PLACES):
        places.acquire()
    try:
        response = sign_in(client)
    finally:
        for _ in range(sessions.HASH_PLACES):
            places.release()
    assert (response.status_code, response.headers["retry-after"]) == (503, "1")


# Deleting an account


def delete_account(client: TestClient, password: str = PASSWORD) -> Response:
    return client.post("/api/account/delete", json={"password": password})


def test_deleting_removes_the_account_and_everything_of_it(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source)
    sign_up(client)
    team_with(client, [6])
    client.post(f"/api/alerts/{add_change(conn)}/dismiss")
    laptop = browser(client)
    sign_in(laptop)
    response = delete_account(client)
    assert response.status_code == 204
    assert "uid" not in client.cookies
    left = [count(conn, f"SELECT count(*) FROM {table}") for table in ("users", "teams")]
    left += [count(conn, f"SELECT count(*) FROM {table}") for table in ("dismissals", "sessions")]
    assert left == [0, 0, 0, 0]
    assert laptop.get("/api/session").json() == {"username": None}
    assert sign_up(browser(client), "misty").status_code == 201


def test_a_wrong_password_deletes_nothing(client: TestClient, conn: psycopg.Connection) -> None:
    sign_up(client)
    response = delete_account(client, "not the password")
    assert (response.status_code, response.json()) == (401, {"detail": "Wrong password."})
    assert count(conn, "SELECT count(*) FROM users") == 1
    assert client.get("/api/session").json() == {"username": "Misty"}


@pytest.mark.parametrize("anonymous", [True, False], ids=["anonymous", "no-cookie"])
def test_a_caller_not_signed_in_to_an_account_gets_401(
    client: TestClient, conn: psycopg.Connection, anonymous: bool
) -> None:
    sign_up(browser(client))
    if anonymous:
        make_teams(client, "t", 1)
    response = delete_account(client)
    assert (response.status_code, response.json()) == (401, {"detail": sessions.NOT_SIGNED_IN})
    assert count(conn, "SELECT count(*) FROM users") == (2 if anonymous else 1)


def test_another_account_sending_a_password_touches_only_itself(
    client: TestClient, conn: psycopg.Connection
) -> None:
    sign_up(client)
    other = browser(client)
    sign_up(other, "Brock", "another long password")
    assert delete_account(other, PASSWORD).status_code == 401
    assert count(conn, "SELECT count(*) FROM users WHERE username = 'Misty'") == 1


def test_the_sixth_delete_from_one_session_is_429_and_another_session_still_deletes(
    client: TestClient, conn: psycopg.Connection
) -> None:
    sign_up(client)
    laptop = browser(client)
    sign_in(laptop)
    answers = [delete_account(client, "a wrong guess").status_code for _ in range(6)]
    assert answers == [401] * 5 + [429]
    assert delete_account(laptop).status_code == 204
    assert count(conn, "SELECT count(*) FROM users") == 0


def test_delete_attempts_leave_the_usernames_sign_in_counts_alone(client: TestClient) -> None:
    sign_up(client)
    for _ in range(5):
        delete_account(client, "a wrong guess")
    stranger = browser(client)
    answers = [sign_in(stranger, "Misty", "a wrong guess").status_code for _ in range(10)]
    assert answers == [401] * 10
