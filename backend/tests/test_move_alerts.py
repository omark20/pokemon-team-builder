"""A change to a move: the scan records it, and it alerts visitors whose team members
carry the move, by choice or as one of a Pokémon's default four.

The stored data is the fake PokéAPI's: 21 Pokémon and 17 moves. Flamethrower (53) is
fire, special, power 90, accuracy 100 in its captured answer.
"""

from datetime import timedelta
from typing import Any

import psycopg
import pytest
from fake_pokeapi import MOVE_LIST, FakePokeApi, move_path, run_fake_scan
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app import db
from app.pokeapi import UpstreamError
from app.routes.alerts import alerts_for
from app.scan import utc_now

ALERTS, TEAMS = "/api/alerts", "/api/teams"
FLAMETHROWER, FOCUS_BLAST, CHARIZARD, MACHAMP, PIKACHU = 53, 411, 6, 68, 25


def move_changes(conn: psycopg.Connection) -> list[tuple[Any, ...]]:
    rows = conn.execute(
        "SELECT move_id, field, old_value, new_value FROM changes"
        " WHERE move_id IS NOT NULL ORDER BY id"
    )
    return rows.fetchall()


def change_flamethrower(source: FakePokeApi, path: tuple[str, ...], value: object) -> None:
    target = source.answers[move_path(FLAMETHROWER)]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("power",), 95, ("power", 90, 95)),
        (("power",), None, ("power", 90, None)),
        (("accuracy",), 85, ("accuracy", 100, 85)),
        (("accuracy",), None, ("accuracy", 100, None)),
        (("type", "name"), "water", ("type", "fire", "water")),
        (("damage_class", "name"), "physical", ("damage_class", "special", "physical")),
    ],
    ids=["power", "power-to-none", "accuracy", "accuracy-to-none", "type", "class"],
)
def test_a_changed_move_field_records_one_change_and_a_first_sighting_none(
    conn: psycopg.Connection,
    source: FakePokeApi,
    path: tuple[str, ...],
    value: object,
    expected: tuple[str, object, object],
) -> None:
    run_fake_scan(conn, source)
    assert move_changes(conn) == []  # every move seen for the first time
    change_flamethrower(source, path, value)
    _, status = run_fake_scan(conn, source)
    assert status == "ok"
    assert move_changes(conn) == [(FLAMETHROWER, *expected)]


def test_a_move_list_that_cannot_be_read_records_no_change(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source)
    change_flamethrower(source, ("power",), 95)
    source.answers[MOVE_LIST] = UpstreamError("http_503", retryable=True)
    run_fake_scan(conn, source)
    assert move_changes(conn) == []


@pytest.fixture
def changed(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> TestClient:
    """A scanned database in which Flamethrower's power then went from 90 to 95."""
    run_fake_scan(conn, source)
    change_flamethrower(source, ("power",), 95)
    run_fake_scan(conn, source)
    return client


def team(client: TestClient, pokemon_ids: list[int], move_ids: list[Any] | None = None) -> None:
    team_id = client.post(TEAMS, json={"name": f"Team {len(client.get(TEAMS).json()) + 1}"})
    body: dict[str, Any] = {"pokemon_ids": pokemon_ids}
    if move_ids is not None:
        body["move_ids"] = move_ids
    path = f"{TEAMS}/{team_id.json()['id']}/members"
    assert client.put(path, json=body).status_code == 200


def default_four(conn: psycopg.Connection, pokemon_id: int) -> list[int]:
    row = conn.execute("SELECT move_ids FROM duel_data WHERE pokemon_id = %s", (pokemon_id,))
    found = row.fetchone()
    assert found is not None
    return list(found[0])


def test_a_pokemon_carrying_the_move_by_default_is_alerted(
    changed: TestClient, conn: psycopg.Connection
) -> None:
    assert FLAMETHROWER in default_four(conn, CHARIZARD)
    team(changed, [CHARIZARD, PIKACHU])
    [alert] = changed.get(ALERTS).json()
    assert alert | {"id": None, "detected_at": None} == {
        "id": None,
        "pokemon_id": None,
        "attacker": None,
        "defender": None,
        "move": "flamethrower",
        "field": "power",
        "old_value": 90,
        "new_value": 95,
        "detected_at": None,
        "is_demo": False,
        "your_pokemon": [CHARIZARD],
    }


def test_a_chosen_move_alerts_and_a_choice_without_it_does_not(
    changed: TestClient, conn: psycopg.Connection
) -> None:
    assert FLAMETHROWER not in default_four(conn, MACHAMP)
    team(changed, [MACHAMP, CHARIZARD], [[FLAMETHROWER], [FOCUS_BLAST]])
    [alert] = changed.get(ALERTS).json()
    assert (alert["move"], alert["your_pokemon"]) == ("flamethrower", [MACHAMP])


def test_able_to_learn_it_without_carrying_it_or_another_visitor_is_not_alerted(
    changed: TestClient, conn: psycopg.Connection
) -> None:
    assert FLAMETHROWER not in default_four(conn, MACHAMP)  # though Machamp can learn it
    team(changed, [MACHAMP])
    assert changed.get(ALERTS).json() == []
    other = TestClient(changed.app, base_url="https://testserver")
    team(other, [PIKACHU])
    assert other.get(ALERTS).json() == []


def test_a_move_alert_goes_after_seven_days_and_when_dismissed(
    changed: TestClient, conn: psycopg.Connection
) -> None:
    team(changed, [CHARIZARD])
    [alert] = changed.get(ALERTS).json()
    user_id = conn.execute("SELECT user_id FROM teams").fetchone()
    assert user_id is not None
    later = utc_now() + timedelta(days=7, minutes=1)
    assert alerts_for(conn, user_id[0], later) == []
    assert changed.post(f"{ALERTS}/{alert['id']}/dismiss").status_code == 204
    assert changed.get(ALERTS).json() == []


# The alert query of the version before moves were alerted on, as it was.
EARLIER_ALERTS_QUERY = """
    WITH mine AS (
        SELECT DISTINCT p.id, p.types
        FROM teams t
        JOIN team_members m ON m.team_id = t.id
        JOIN pokemon p ON p.id = m.pokemon_id
        WHERE t.user_id = %(user_id)s
    )
    SELECT c.id, c.pokemon_id, c.attacker, c.defender, c.field, c.old_value, c.new_value,
           c.detected_at, c.is_demo, array_agg(DISTINCT mine.id ORDER BY mine.id) AS your_pokemon
    FROM changes c
    JOIN mine ON c.pokemon_id = mine.id
              OR c.attacker = ANY (mine.types)
              OR c.defender = ANY (mine.types)
    WHERE c.detected_at > %(now)s - interval '7 days'
      AND NOT EXISTS (
          SELECT 1 FROM dismissals d WHERE d.user_id = %(user_id)s AND d.change_id = c.id
      )
    GROUP BY c.id
    ORDER BY c.detected_at DESC, c.id DESC
    LIMIT %(limit)s
"""


def test_the_earlier_alert_query_neither_breaks_on_a_move_change_nor_shows_it(
    changed: TestClient, conn: psycopg.Connection
) -> None:
    team(changed, [CHARIZARD])
    user_id = conn.execute("SELECT user_id FROM teams").fetchone()
    assert user_id is not None and move_changes(conn) != []
    params = {"user_id": user_id[0], "now": utc_now(), "limit": 100}
    assert conn.cursor(row_factory=dict_row).execute(EARLIER_ALERTS_QUERY, params).fetchall() == []


OLD_CHECKS = (
    "ALTER TABLE changes ADD CHECK ((pokemon_id IS NULL) <> (attacker IS NULL)),"
    " ADD CHECK ((attacker IS NULL) = (defender IS NULL))"
)


def check_names(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'changes'::regclass AND contype = 'c'"
    )
    return {name for (name,) in rows}


def test_the_migration_replaces_the_old_checks_once_and_keeps_every_row(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi, database_url: str
) -> None:
    run_fake_scan(conn, source)
    conn.execute("ALTER TABLE changes DROP CONSTRAINT changes_about_one_thing")
    conn.execute("ALTER TABLE changes DROP COLUMN move_id")
    conn.execute(OLD_CHECKS)  # the table as the version before made it
    run = conn.execute("SELECT max(id) FROM scan_runs").fetchone()
    assert run is not None
    for pokemon_id, attacker, defender in [(CHARIZARD, None, None), (None, "fire", "grass")]:
        conn.execute(
            "INSERT INTO changes (pokemon_id, attacker, defender, field, old_value, new_value,"
            " detected_at, scan_run_id) VALUES (%s, %s, %s, 'x', '1', '2', now(), %s)",
            (pokemon_id, attacker, defender, run[0]),
        )
    assert check_names(conn) == {"changes_check", "changes_check1"}
    for _ in range(2):  # every start applies the schema; the second changes nothing
        with db.connect(database_url) as schema_conn:
            db.apply_schema(schema_conn)
    assert check_names(conn) == {"changes_about_one_thing"}
    assert conn.execute("SELECT count(*) FROM changes").fetchone() == (2,)
    insert = (
        "INSERT INTO changes (pokemon_id, move_id, field, old_value, new_value, detected_at,"
        " scan_run_id) VALUES (%s, %s, 'power', '90', '95', now(), %s)"
    )
    conn.execute(insert, (None, FLAMETHROWER, run[0]))  # a move change is now allowed
    with pytest.raises(psycopg.errors.CheckViolation):  # about two things at once is not
        conn.execute(insert, (CHARIZARD, FLAMETHROWER, run[0]))
