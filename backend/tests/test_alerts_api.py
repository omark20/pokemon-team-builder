"""Alerts: which visitor sees which change, the 7-day window, dismissal, and order.

Change rows are written directly here; the scan that writes them is tested in
test_scan.py. Charizard (6) is fire and flying, Venusaur (3) grass and poison, Pikachu
(25) electric (the captured responses in samples/).
"""

import itertools
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fake_pokeapi import FakePokeApi, run_fake_scan
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.routes.alerts import alerts_for

ALERTS = "/api/alerts"
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


@pytest.fixture
def visitor(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> TestClient:
    run_fake_scan(conn, source)
    return client


@pytest.fixture
def other(visitor: TestClient) -> TestClient:
    """A second visitor: the same running app, a separate cookie jar."""
    return TestClient(visitor.app, base_url="https://testserver")


TEAM_NUMBERS = itertools.count(1)  # a visitor's team names must differ


def team_with(client: TestClient, pokemon_ids: list[int]) -> int:
    name = f"Team {next(TEAM_NUMBERS)}"
    team_id: int = client.post("/api/teams", json={"name": name}).json()["id"]
    client.put(f"/api/teams/{team_id}/members", json={"pokemon_ids": pokemon_ids})
    return team_id


def add_change(
    conn: psycopg.Connection,
    cell: tuple[str, str] | None = None,
    detected_at: datetime | None = None,
) -> int:
    """A change row: Charizard's attack 84 to 94, or a chart cell going from 2 to 1."""
    run = conn.execute("INSERT INTO scan_runs (status, scope) VALUES ('ok', 'full') RETURNING id")
    run_row = run.fetchone()
    assert run_row is not None
    pokemon_id, (attacker, defender) = (None, cell) if cell else (6, (None, None))
    field, old, new = ("multiplier", 2, 1) if cell else ("attack", 84, 94)
    row = conn.execute(
        "INSERT INTO changes (pokemon_id, attacker, defender, field, old_value, new_value,"
        " detected_at, scan_run_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (pokemon_id, attacker, defender, field, Jsonb(old), Jsonb(new))
        + (detected_at or datetime.now(UTC), run_row[0]),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_a_change_reaches_the_visitor_with_that_pokemon_and_no_one_else(
    visitor: TestClient, other: TestClient, conn: psycopg.Connection
) -> None:
    team_with(visitor, [6])
    team_with(other, [25])
    change_id = add_change(conn)
    [alert] = visitor.get(ALERTS).json()
    assert alert | {"detected_at": None} == {
        "id": change_id,
        "pokemon_id": 6,
        "attacker": None,
        "defender": None,
        "field": "attack",
        "old_value": 84,
        "new_value": 94,
        "detected_at": None,
        "is_demo": False,
        "your_pokemon": [6],
    }
    assert other.get(ALERTS).json() == []


@pytest.mark.parametrize(
    ("age", "shown"),
    [
        (timedelta(days=6), True),
        (timedelta(days=7) - timedelta(seconds=1), True),
        (timedelta(days=7), False),
        (timedelta(days=8), False),
    ],
    ids=["6-days", "7-days-less-a-second", "exactly-7-days", "8-days"],
)
def test_only_changes_less_than_7_days_old_are_shown(
    visitor: TestClient, conn: psycopg.Connection, age: timedelta, shown: bool
) -> None:
    team_with(visitor, [6])
    add_change(conn, detected_at=NOW - age)
    [(user_id,)] = conn.execute("SELECT id FROM users").fetchall()
    assert len(alerts_for(conn, user_id, NOW)) == (1 if shown else 0)


def test_a_dismissal_lasts_and_is_for_that_visitor_only(
    visitor: TestClient, other: TestClient, conn: psycopg.Connection
) -> None:
    team_with(visitor, [6])
    team_with(other, [6])
    change_id = add_change(conn)
    for _ in range(2):  # repeating a dismissal is harmless
        assert visitor.post(f"{ALERTS}/{change_id}/dismiss").status_code == 204
    assert visitor.get(ALERTS).json() == []
    assert len(other.get(ALERTS).json()) == 1


def test_dismissing_without_a_cookie_or_an_unknown_change_is_404(
    visitor: TestClient, other: TestClient, conn: psycopg.Connection
) -> None:
    team_with(visitor, [6])
    change_id = add_change(conn)
    assert other.post(f"{ALERTS}/{change_id}/dismiss").status_code == 404
    assert visitor.post(f"{ALERTS}/{change_id + 1}/dismiss").status_code == 404


def test_alerts_follow_the_teams_the_visitor_has_now(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_id = team_with(visitor, [25])
    add_change(conn)
    visitor.put(f"/api/teams/{team_id}/members", json={"pokemon_ids": [6]})
    assert len(visitor.get(ALERTS).json()) == 1
    visitor.put(f"/api/teams/{team_id}/members", json={"pokemon_ids": [25]})
    assert visitor.get(ALERTS).json() == []


def test_a_pokemon_in_several_slots_and_teams_gives_one_alert_naming_it_once(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_with(visitor, [6, 6, 6])
    team_with(visitor, [6, 25])
    add_change(conn)
    [alert] = visitor.get(ALERTS).json()
    assert alert["your_pokemon"] == [6]


def test_a_chart_change_reaches_visitors_with_either_type_only(
    visitor: TestClient, other: TestClient, conn: psycopg.Connection
) -> None:
    team_with(visitor, [6])  # fire
    team_with(other, [3])  # grass
    third = TestClient(visitor.app, base_url="https://testserver")
    team_with(third, [25])  # electric
    add_change(conn, cell=("fire", "grass"))
    assert third.get(ALERTS).json() == []
    assert [alert["your_pokemon"] for alert in visitor.get(ALERTS).json()] == [[6]]
    assert [alert["your_pokemon"] for alert in other.get(ALERTS).json()] == [[3]]


def test_several_changes_come_back_together_newest_first(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_with(visitor, [6])
    now = datetime.now(UTC)
    middle = add_change(conn, detected_at=now - timedelta(hours=2))
    newest = add_change(conn, detected_at=now - timedelta(hours=1))
    oldest = add_change(conn, detected_at=now - timedelta(hours=3))
    assert [alert["id"] for alert in visitor.get(ALERTS).json()] == [newest, middle, oldest]
