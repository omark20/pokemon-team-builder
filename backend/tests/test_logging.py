"""What reaches the log: never a secret, a cookie or a request body; always enough to debug.

The flows are run through the real app with the log captured, then the captured text is
searched for each secret value used.
"""

import logging
from collections.abc import Callable
from pathlib import Path

import psycopg
import pytest
from conftest import ADMIN_TOKEN, SCAN_TOKEN
from fake_pokeapi import FakePokeApi, pokemon_path, run_fake_scan
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.conninfo import conninfo_to_dict

from app import auth
from app.config import Settings
from app.pokeapi import UpstreamError
from app.routes import counter, teams

APP = Path(__file__).resolve().parents[1] / "app"
TEAMS = "/api/teams"
SECRET_NAME = "Secret team name 7f3a"
WRONG_TOKEN = "wrong-token-9b1c"

Forcing = Callable[[pytest.MonkeyPatch, TestClient, Settings], Response]


def force_handler_error(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, _: Settings
) -> Response:
    """A handler that fails with the request body in its exception's message."""

    def fail(*args: object) -> None:
        raise ValueError(f"request body was {SECRET_NAME}")

    monkeypatch.setattr(teams, "_team", fail)
    return client.post(TEAMS, json={"name": SECRET_NAME})


def force_database_error(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, settings: Settings
) -> Response:
    """A database failure whose message quotes the connection string."""

    def fail(*args: object) -> None:
        raise psycopg.OperationalError(f"connection to {settings.database_url} failed")

    monkeypatch.setattr(auth, "current_user", fail)
    return client.get(TEAMS)


@pytest.fixture
def stocked(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> TestClient:
    run_fake_scan(conn, source)
    return client


def test_no_secret_cookie_or_request_body_reaches_the_log(
    stocked: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        stocked.post("/api/admin/scan", headers={"Authorization": f"Bearer {WRONG_TOKEN}"})
        team = stocked.post(TEAMS, json={"name": SECRET_NAME}).json()
        stocked.put(f"{TEAMS}/{team['id']}/members", json={"pokemon_ids": [131, 248]})
        force_handler_error(monkeypatch, stocked, settings)
        force_database_error(monkeypatch, stocked, settings)
    database = conninfo_to_dict(settings.database_url)
    # The database user is "pokemon", which is also an ordinary word in these lines.
    secrets = [WRONG_TOKEN, SCAN_TOKEN, ADMIN_TOKEN, stocked.cookies["uid"], SECRET_NAME]
    secrets += [settings.database_url, str(database["password"]), str(database["dbname"])]
    secrets += ["Authorization", "131, 248"]
    assert "admin_unauthorized" in caplog.text
    assert [secret for secret in secrets if secret in caplog.text] == []


def test_account_flows_log_no_username_password_hash_or_cookie(
    client: TestClient, conn: psycopg.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    name, password, guess = "Kasumi7f3a", "correct horse 2e9d", "wrong guess 5c1d"
    laptop = TestClient(client.app, base_url="https://testserver")
    with caplog.at_level(logging.INFO):
        client.post("/api/account", json={"username": name, "password": password})
        laptop.post("/api/session", json={"username": name, "password": guess})
        laptop.post("/api/session", json={"username": name.upper(), "password": password})
        cookies = [client.cookies["uid"], laptop.cookies["uid"]]
        laptop.delete("/api/session")
        row = conn.execute("SELECT password_hash FROM users").fetchone()
        client.post("/api/account/delete", json={"password": password})
    assert row is not None
    secrets = [name, name.lower(), name.upper(), password, guess, row[0], *cookies]
    events = ["account_created", "sign_in_failed", "signed_in", "signed_out", "account_deleted"]
    assert [event for event in events if f" {event} " not in caplog.text] == []
    assert [secret for secret in secrets if secret in caplog.text] == []


@pytest.mark.parametrize(("header", "logged"), [(None, "absent"), (WRONG_TOKEN, "wrong")])
def test_an_admin_refusal_says_whether_a_token_was_absent_or_wrong(
    client: TestClient, caplog: pytest.LogCaptureFixture, header: str | None, logged: str
) -> None:
    headers = {} if header is None else {"Authorization": f"Bearer {header}"}
    with caplog.at_level(logging.INFO):
        client.post("/api/admin/scan", headers=headers)
    [line] = [message for message in caplog.messages if "admin_unauthorized" in message]
    assert line.endswith(f"route=/api/admin/scan token={logged}")


@pytest.mark.parametrize(
    ("force", "error_class"),
    [(force_handler_error, "ValueError"), (force_database_error, "OperationalError")],
)
def test_a_forced_error_is_logged_with_its_class_and_frames(
    stocked: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    force: Forcing,
    error_class: str,
) -> None:
    with caplog.at_level(logging.INFO):
        response = force(monkeypatch, stocked, settings)
    request_id = response.json()["request_id"]
    [line] = [message for message in caplog.messages if "request_failed" in message]
    assert f"request_id={request_id}" in line
    assert f"route={TEAMS} error_class={error_class} frames=" in line
    assert "test_logging.py:" in line and ":fail" in line


def _line_break_in_path(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> None:
    client.post("/api/admin/scan?next=%0AWARNING%20forged=1")


def _line_break_in_upstream_name(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    fire = source.answers["type/10/"]["damage_relations"]
    fire["double_damage_to"].append({"name": "fire\nWARNING forged=1"})
    run_fake_scan(conn, source)


@pytest.mark.parametrize(
    ("send", "event"),
    [(_line_break_in_path, "admin_unauthorized"), (_line_break_in_upstream_name, "chart_rejected")],
)
def test_a_line_break_from_outside_cannot_start_a_new_log_line(
    client: TestClient,
    conn: psycopg.Connection,
    source: FakePokeApi,
    caplog: pytest.LogCaptureFixture,
    send: Callable[[TestClient, psycopg.Connection, FakePokeApi], None],
    event: str,
) -> None:
    with caplog.at_level(logging.INFO):
        send(client, conn, source)
    assert [message for message in caplog.messages if "\n" in message] == []
    assert len([message for message in caplog.messages if event in message]) == 1


def test_only_the_helper_logs_exceptions() -> None:
    for module in APP.rglob("*.py"):
        text = module.read_text()
        assert "logger.exception" not in text, module
        assert module.name == "logs.py" or "exc_info" not in text, module


def test_a_failing_scan_is_explained_by_its_log_lines(
    conn: psycopg.Connection, source: FakePokeApi, caplog: pytest.LogCaptureFixture
) -> None:
    run_fake_scan(conn, source)
    source.answers[pokemon_path(6)] = UpstreamError("timeout", retryable=True)
    source.answers[pokemon_path(25)] = UpstreamError("http_500", retryable=True)
    source.answers[pokemon_path(9)] = {"not": "a pokemon"}
    with caplog.at_level(logging.INFO):
        run_id, _ = run_fake_scan(conn, source)
    lines = [message for message in caplog.messages if f"run_id={run_id}" in message]
    assert lines[0] == f"scan_started run_id={run_id} scope=full"
    assert sum("upstream_retry" in line and "reason=timeout" in line for line in lines) == 3
    assert sum("upstream_retry" in line and "reason=http_500" in line for line in lines) == 3
    assert {line for line in lines if "pokemon_skipped" in line} == {
        f"pokemon_skipped run_id={run_id} pokemon_id=6 reason=timeout",
        f"pokemon_skipped run_id={run_id} pokemon_id=9 reason=parse_error rule=malformed",
        f"pokemon_skipped run_id={run_id} pokemon_id=25 reason=http_500",
    }
    row = conn.execute(
        "SELECT status, scanned, changed, failed FROM scan_runs WHERE id = %s", (run_id,)
    ).fetchone()
    assert row == ("incomplete", 11, 0, 3)
    summary = "status=incomplete scanned=11 changed=0 failed=3 filled=0"
    assert summary in lines[-1] and lines[-1].startswith(f"scan_finished run_id={run_id}")


def _refuse_admin(client: TestClient, _: pytest.MonkeyPatch) -> None:
    client.post("/api/admin/scan", headers={"Authorization": f"Bearer {WRONG_TOKEN}"})


def _refuse_counter(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(counter, "COUNTER_WAIT_SECONDS", 0.01)
    team = client.post(TEAMS, json={"name": "Busy"}).json()
    client.put(f"{TEAMS}/{team['id']}/members", json={"pokemon_ids": [6]})
    places = client.app.state.counter_places
    assert places.acquire(blocking=False) and places.acquire(blocking=False)
    try:
        client.get(f"{TEAMS}/{team['id']}/counter")
    finally:
        places.release()
        places.release()


@pytest.mark.parametrize(
    ("refuse", "event"),
    [(_refuse_admin, "admin_unauthorized"), (_refuse_counter, "counter_busy")],
)
def test_a_repeated_refusal_is_logged_once_per_address_per_window(
    stocked: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    refuse: Callable[[TestClient, pytest.MonkeyPatch], None],
    event: str,
) -> None:
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            refuse(stocked, monkeypatch)
    assert len([message for message in caplog.messages if event in message]) == 1
