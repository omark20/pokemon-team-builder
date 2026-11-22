"""The admin endpoints: which token opens which, and the demo path end to end.

The demo patches go through the ordinary scan, here against the fake PokéAPI built from
samples/. Charizard (6) has attack 84, defence 78 and types fire and flying; fire does
double damage to grass.
"""

from typing import Any

import psycopg
import pytest
from conftest import ADMIN_TOKEN, SCAN_TOKEN
from fake_pokeapi import FakePokeApi, pokemon_path, run_fake_scan
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SCAN = "/api/admin/scan"
OVERRIDES = "/api/admin/demo/overrides"
RESET = "/api/admin/demo/reset"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
ATTACK_94 = {"pokemon": {"6": {"attack": 94}}, "type_chart": []}


@pytest.fixture
def stocked(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> TestClient:
    """The captured Pokémon stored, and a visitor whose team holds Charizard."""
    run_fake_scan(conn, source)
    team_id = client.post("/api/teams", json={"name": "Team"}).json()["id"]
    client.put(f"/api/teams/{team_id}/members", json={"pokemon_ids": [6]})
    return client


def demo_scan(conn: psycopg.Connection, source: FakePokeApi) -> None:
    run_fake_scan(conn, source, pokemon_ids=[6, 25])


def stored_data(conn: psycopg.Connection) -> list[tuple[Any, ...]]:
    """Every stored Pokémon value and chart cell, without the update times."""
    pokemon = conn.execute(
        "SELECT id, name, types, hp, attack, defense, special_attack, special_defense, speed,"
        " sprite_url, removed_at FROM pokemon ORDER BY id"
    ).fetchall()
    return pokemon + conn.execute("SELECT * FROM type_effectiveness ORDER BY 1, 2").fetchall()


def change_fields(conn: psycopg.Connection) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT field, old_value, new_value, is_demo FROM changes ORDER BY id"
    ).fetchall()


@pytest.mark.parametrize(
    ("method", "path", "token"),
    [
        ("POST", SCAN, None),
        ("POST", SCAN, "wrong-token"),
        ("POST", SCAN, ADMIN_TOKEN),
        ("POST", SCAN, "ünïcode"),
        ("PUT", OVERRIDES, None),
        ("PUT", OVERRIDES, "wrong-token"),
        ("PUT", OVERRIDES, SCAN_TOKEN),
        ("POST", RESET, None),
        ("POST", RESET, "wrong-token"),
        ("POST", RESET, SCAN_TOKEN),
    ],
)
def test_each_admin_endpoint_opens_only_to_its_own_token(
    client: TestClient, conn: psycopg.Connection, method: str, path: str, token: str | None
) -> None:
    # Bytes, so that a non-ASCII token can be sent at all.
    headers = {} if token is None else {"Authorization": f"Bearer {token}".encode()}
    assert client.request(method, path, headers=headers, json=ATTACK_94).status_code == 401
    assert conn.execute("SELECT count(*) FROM scan_runs").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM demo_overrides").fetchone() == (0,)


@pytest.mark.parametrize(
    ("method", "path", "token"),
    [("POST", SCAN, SCAN_TOKEN), ("PUT", OVERRIDES, ADMIN_TOKEN), ("POST", RESET, ADMIN_TOKEN)],
)
def test_an_endpoint_whose_token_is_unset_stays_closed(
    database_url: str, method: str, path: str, token: str
) -> None:
    settings = Settings(database_url=database_url, scan_token=None, admin_token=None)
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        for header in ({}, {"Authorization": f"Bearer {token}"}, {"Authorization": "Bearer "}):
            assert client.request(method, path, headers=header, json=ATTACK_94).status_code == 401


def test_storing_overrides_alone_changes_nothing(
    stocked: TestClient, conn: psycopg.Connection
) -> None:
    before = stored_data(conn)
    assert stocked.put(OVERRIDES, headers=ADMIN, json=ATTACK_94).status_code == 200
    assert stored_data(conn) == before
    assert change_fields(conn) == []
    assert stocked.get("/api/alerts").json() == []


def test_overrides_then_a_scan_give_a_demo_change_and_its_alert(
    stocked: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    stocked.put(OVERRIDES, headers=ADMIN, json=ATTACK_94)
    demo_scan(conn, source)
    assert change_fields(conn) == [("attack", 84, 94, True)]
    [alert] = stocked.get("/api/alerts").json()
    assert (alert["field"], alert["is_demo"], alert["your_pokemon"]) == ("attack", True, [6])


def test_a_real_change_in_the_same_scan_is_not_demo_and_survives_reset(
    stocked: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    stocked.put(OVERRIDES, headers=ADMIN, json=ATTACK_94)
    source.answers[pokemon_path(6)]["stats"][2]["base_stat"] = 80  # defence really changes
    demo_scan(conn, source)
    stocked.post(RESET, headers=ADMIN)
    assert change_fields(conn) == [("defense", 78, 80, False)]
    stats = conn.execute("SELECT attack, defense FROM pokemon WHERE id = 6").fetchone()
    assert stats == (84, 80)


def test_reset_restores_every_patched_value_and_the_next_scan_records_nothing(
    stocked: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    before = stored_data(conn)
    doc = {
        "pokemon": {
            "6": {"attack": 94, "types": ["fire", "dragon"], "sprite_url": None},
            "25": {"removed": True},
        },
        "type_chart": [{"attacker": "fire", "defender": "grass", "multiplier": 1}],
    }
    stocked.put(OVERRIDES, headers=ADMIN, json=doc)
    demo_scan(conn, source)
    assert len(change_fields(conn)) == 5
    assert stocked.post(RESET, headers=ADMIN).json() == {"restored": 5, "deleted": 5}
    assert stored_data(conn) == before
    assert conn.execute("SELECT count(*) FROM demo_overrides").fetchone() == (0,)
    run_fake_scan(conn, source)
    assert change_fields(conn) == []


def test_two_injections_on_one_field_unwind_to_the_original(
    stocked: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    for attack in (94, 99):
        stocked.put(OVERRIDES, headers=ADMIN, json={"pokemon": {"6": {"attack": attack}}})
        demo_scan(conn, source)
    stocked.post(RESET, headers=ADMIN)
    assert conn.execute("SELECT attack FROM pokemon WHERE id = 6").fetchone() == (84,)
    assert change_fields(conn) == []


def test_demo_active_is_true_from_the_first_override_until_reset(
    stocked: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    def demo_active() -> bool:
        active: bool = stocked.get("/api/scan/status").json()["demo_active"]
        return active

    assert demo_active() is False
    stocked.put(OVERRIDES, headers=ADMIN, json=ATTACK_94)
    assert demo_active() is True
    demo_scan(conn, source)
    assert demo_active() is True
    stocked.post(RESET, headers=ADMIN)
    assert demo_active() is False


@pytest.mark.parametrize(
    "doc",
    [
        {"pokemon": {"6": {"types": ["stellar"]}}},
        {"pokemon": {"6": {"types": ["fire", "fire"]}}},
        {"pokemon": {"6": {"attack": 256}}},
        {"pokemon": {"6": {"attack": "94"}}},
        {"pokemon": {"6": {"sprite_url": "https://example.com/6.png"}}},
        {"pokemon": {"6": {"name": None}}},
        {"pokemon": {"6": {"removed": False}}},
        {"pokemon": {"6": {"weight": 905}}},
        {"pokemon": {"7": {"attack": 94}}},
        {"pokemon": {str(pokemon_id): {"attack": 94} for pokemon_id in range(1, 22)}},
        {"type_chart": [{"attacker": "fire", "defender": "grass", "multiplier": 3}]},
        {"type_chart": [{"attacker": "fire", "defender": "grass", "multiplier": True}]},
    ],
    ids=[
        "unknown-type", "repeated-type", "stat-256", "stat-as-text", "foreign-sprite",
        "null-name", "removed-false", "unknown-field", "unknown-pokemon", "21-pokemon",
        "multiplier-3", "multiplier-true",
    ],
)  # fmt: skip
def test_an_override_that_real_data_could_not_contain_is_422(
    stocked: TestClient, conn: psycopg.Connection, doc: dict[str, Any]
) -> None:
    assert stocked.put(OVERRIDES, headers=ADMIN, json=doc).status_code == 422
    assert conn.execute("SELECT count(*) FROM demo_overrides").fetchone() == (0,)


@pytest.mark.parametrize(
    "doc",
    [
        {"pokemon": {"6": {"attack": 94}}},
        {"pokemon": {"25": {"removed": True}}},
        {"type_chart": [{"attacker": "fire", "defender": "grass", "multiplier": 1}]},
    ],
    ids=["stat", "removal", "chart-cell"],
)
def test_undoing_a_demo_value_without_reset_is_still_demo_and_reset_removes_it(
    stocked: TestClient, conn: psycopg.Connection, source: FakePokeApi, doc: dict[str, Any]
) -> None:
    before = stored_data(conn)
    stocked.put(OVERRIDES, headers=ADMIN, json=doc)
    demo_scan(conn, source)
    stocked.put(OVERRIDES, headers=ADMIN, json={"pokemon": {}, "type_chart": []})  # no reset
    demo_scan(conn, source)
    assert [is_demo for *_, is_demo in change_fields(conn)] == [True, True]
    assert stocked.post(RESET, headers=ADMIN).json() == {"restored": 2, "deleted": 2}
    assert stored_data(conn) == before
    assert change_fields(conn) == []
