"""The scan against a fake PokéAPI built from samples/, on the real test database.

Expected values are read off the captured responses: Charizard (id 6) has attack 84 and
types fire and flying; fire does double damage to grass.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fake_pokeapi import POKEMON_LIST, FakePokeApi, pokemon_path

from app.domain.diff import RECORD_FIELDS
from app.pokeapi import UpstreamError
from app.scan import run_scan, start_run, utc_now

CHARIZARD = pokemon_path(6)
FIXED_TIME = datetime(2026, 11, 20, 9, 17, tzinfo=UTC)
Breaker = Callable[[FakePokeApi], None]


@pytest.fixture
def source() -> FakePokeApi:
    return FakePokeApi()


def scan(conn: psycopg.Connection, source: FakePokeApi, **options: Any) -> tuple[int, str]:
    """Start and run one scan with no waits between retries; its run ID and status."""
    scope = "full" if options.get("pokemon_ids") is None else "subset"
    run_id = start_run(conn, scope, utc_now())
    return run_id, run_scan(conn, source, run_id, retry_waits=(0, 0, 0), **options)


def pokemon_rows(conn: psycopg.Connection) -> list[tuple[Any, ...]]:
    return conn.execute("SELECT * FROM pokemon ORDER BY id").fetchall()


def change_rows(conn: psycopg.Connection) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT pokemon_id, attacker, defender, field, old_value, new_value"
        " FROM changes ORDER BY id"
    ).fetchall()


def chart_rows(conn: psycopg.Connection) -> list[tuple[Any, ...]]:
    return conn.execute("SELECT * FROM type_effectiveness ORDER BY attacker, defender").fetchall()


def type_relations(source: FakePokeApi, type_id: int) -> dict[str, list[dict[str, str]]]:
    relations: dict[str, list[dict[str, str]]] = source.answers[f"type/{type_id}/"][
        "damage_relations"
    ]
    return relations


def without(entries: list[dict[str, str]], name: str) -> list[dict[str, str]]:
    return [entry for entry in entries if entry["name"] != name]


def test_first_run_stores_everything_and_records_no_change(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_id, status = scan(conn, source)
    assert status == "ok"
    assert len(pokemon_rows(conn)) == 14
    assert len(chart_rows(conn)) == 324
    assert change_rows(conn) == []
    run = conn.execute("SELECT scanned, changed, failed FROM scan_runs WHERE id = %s", (run_id,))
    assert run.fetchone() == (14, 0, 0)


def test_second_run_on_the_same_data_writes_nothing(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    scan(conn, source)
    before = (pokemon_rows(conn), chart_rows(conn))
    _, status = scan(conn, source)
    assert status == "ok"
    assert (pokemon_rows(conn), chart_rows(conn)) == before
    assert change_rows(conn) == []


def _attack_94(source: FakePokeApi) -> None:
    source.answers[CHARIZARD]["stats"][1]["base_stat"] = 94


def _fire_only(source: FakePokeApi) -> None:
    source.answers[CHARIZARD]["types"].pop()


@pytest.mark.parametrize(
    ("change", "field", "old", "new"),
    [(_attack_94, "attack", 84, 94), (_fire_only, "types", ["fire", "flying"], ["fire"])],
)
def test_a_changed_field_records_one_change_and_updates_the_row(
    conn: psycopg.Connection, source: FakePokeApi, change: Breaker, field: str, old: Any, new: Any
) -> None:
    scan(conn, source)
    change(source)
    run_id, _ = scan(conn, source, now=lambda: FIXED_TIME)
    assert change_rows(conn) == [(6, None, None, field, old, new)]
    detected = conn.execute("SELECT detected_at, scan_run_id FROM changes").fetchone()
    assert detected == (FIXED_TIME, run_id)
    stored = conn.execute(f"SELECT {field} FROM pokemon WHERE id = 6").fetchone()
    assert stored == (new,)


def test_a_changed_chart_cell_records_one_change(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    scan(conn, source)
    fire, grass = type_relations(source, 10), type_relations(source, 12)
    fire["double_damage_to"] = without(fire["double_damage_to"], "grass")
    grass["double_damage_from"] = without(grass["double_damage_from"], "fire")
    scan(conn, source)
    assert change_rows(conn) == [(None, "fire", "grass", "multiplier", 2, 1)]
    cell = conn.execute(
        "SELECT multiplier FROM type_effectiveness WHERE attacker = 'fire' AND defender = 'grass'"
    )
    assert cell.fetchone() == (1.0,)


@pytest.mark.parametrize(
    ("answer", "attempts"),
    [
        (UpstreamError("timeout", retryable=True), 4),
        (UpstreamError("http_500", retryable=True), 4),
        ({"unexpected": "body"}, 1),
    ],
    ids=["timeout", "server-error", "garbage-body"],
)
def test_a_pokemon_that_cannot_be_read_is_skipped_and_left_as_stored(
    conn: psycopg.Connection, source: FakePokeApi, answer: object, attempts: int
) -> None:
    scan(conn, source)
    before = pokemon_rows(conn)
    source.answers[CHARIZARD] = answer
    source.requested.clear()
    run_id, status = scan(conn, source)
    assert status == "incomplete"
    assert source.requested.count(CHARIZARD) == attempts
    assert pokemon_rows(conn) == before
    assert change_rows(conn) == []
    failed = conn.execute("SELECT failed FROM scan_runs WHERE id = %s", (run_id,)).fetchone()
    assert failed == (1,)


def _list_errors(source: FakePokeApi) -> None:
    source.answers[POKEMON_LIST] = UpstreamError("http_503", retryable=True)


def _count_disagrees(source: FakePokeApi) -> None:
    source.answers[POKEMON_LIST]["count"] += 1


def _list_shrinks(source: FakePokeApi) -> None:
    # 12 of 14 stored is under 90%.
    del source.answers[POKEMON_LIST]["results"][:2]
    source.answers[POKEMON_LIST]["count"] -= 2


@pytest.mark.parametrize("break_list", [_list_errors, _count_disagrees, _list_shrinks])
def test_an_untrustworthy_list_fails_the_run_and_touches_nothing(
    conn: psycopg.Connection, source: FakePokeApi, break_list: Breaker
) -> None:
    scan(conn, source)
    before = pokemon_rows(conn)
    break_list(source)
    source.requested.clear()
    _, status = scan(conn, source)
    assert status == "failed"
    assert not any(path.startswith("pokemon/") for path in source.requested)
    assert pokemon_rows(conn) == before
    assert change_rows(conn) == []


def test_an_invalid_chart_leaves_the_stored_chart_untouched(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    scan(conn, source)
    before = chart_rows(conn)
    fire = type_relations(source, 10)
    fire["double_damage_from"] = without(fire["double_damage_from"], "water")
    _, status = scan(conn, source)
    assert status == "incomplete"
    assert chart_rows(conn) == before
    assert change_rows(conn) == []


def test_a_404_flags_the_pokemon_removed_and_its_return_restores_it(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    scan(conn, source)
    pikachu = source.answers[pokemon_path(25)]
    source.answers[pokemon_path(25)] = None
    scan(conn, source)
    flagged = conn.execute("SELECT name, removed_at IS NOT NULL FROM pokemon WHERE id = 25")
    assert flagged.fetchone() == ("pikachu", True)
    source.answers[pokemon_path(25)] = pikachu
    scan(conn, source)
    restored = conn.execute("SELECT removed_at FROM pokemon WHERE id = 25").fetchone()
    assert restored == (None,)
    assert change_rows(conn) == [
        (25, None, None, "status", "available", "removed"),
        (25, None, None, "status", "removed", "available"),
    ]


def test_more_than_20_removals_in_one_run_are_not_applied(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    for pokemon_id in range(2001, 2022):
        source.add_pokemon(pokemon_id)
    scan(conn, source)
    for pokemon_id in range(2001, 2022):
        source.answers[pokemon_path(pokemon_id)] = None
    _, status = scan(conn, source)
    assert status == "incomplete"
    flagged = conn.execute("SELECT count(*) FROM pokemon WHERE removed_at IS NOT NULL")
    assert flagged.fetchone() == (0,)
    assert change_rows(conn) == []


def test_pokemon_ids_narrows_the_run_and_judges_nothing_removed(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    scan(conn, source)
    source.answers[POKEMON_LIST]["results"].pop()  # one listed Pokémon disappears
    source.answers[POKEMON_LIST]["count"] -= 1
    source.requested.clear()
    run_id, status = scan(conn, source, pokemon_ids=[6])
    assert status == "ok"
    assert [path for path in source.requested if path.startswith("pokemon/")] == [CHARIZARD]
    assert change_rows(conn) == []
    scope = conn.execute("SELECT scope, scanned FROM scan_runs WHERE id = %s", (run_id,))
    assert scope.fetchone() == ("subset", 1)


def test_a_newly_added_empty_column_is_filled_without_a_change(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    scan(conn, source)
    before = pokemon_rows(conn)
    # What a column added with ALTER TABLE ... ADD COLUMN looks like: NULL in every row.
    conn.execute("ALTER TABLE pokemon ALTER COLUMN speed DROP NOT NULL")
    conn.execute("UPDATE pokemon SET speed = NULL")
    scan(conn, source)
    speeds = conn.execute("SELECT speed FROM pokemon WHERE id = 6").fetchone()
    assert speeds == (100,)
    assert change_rows(conn) == []
    filled = pokemon_rows(conn)
    scan(conn, source)
    assert pokemon_rows(conn) == filled
    assert [row[:10] for row in filled] == [row[:10] for row in before]


@pytest.mark.parametrize(("before", "after"), [("url", None), (None, "url")])
def test_a_sprite_appearing_or_disappearing_is_a_json_null_change(
    conn: psycopg.Connection, source: FakePokeApi, before: str | None, after: str | None
) -> None:
    sprite = source.answers[CHARIZARD]["sprites"]["front_default"]
    source.answers[CHARIZARD]["sprites"]["front_default"] = sprite if before else None
    scan(conn, source)
    source.answers[CHARIZARD]["sprites"]["front_default"] = sprite if after else None
    scan(conn, source)
    assert change_rows(conn) == [
        (6, None, None, "sprite_url", sprite if before else None, sprite if after else None)
    ]
    kinds = conn.execute("SELECT jsonb_typeof(old_value), jsonb_typeof(new_value) FROM changes")
    expected_kinds = ("string", "null") if before else ("null", "string")
    assert kinds.fetchone() == expected_kinds


def test_every_record_field_is_a_column_of_the_pokemon_table(conn: psycopg.Connection) -> None:
    columns = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'pokemon'"
    )
    assert set(RECORD_FIELDS) <= {name for (name,) in columns}


@pytest.mark.parametrize(("minutes_ago", "cut_off"), [(31, True), (29, False)])
def test_a_run_left_running_over_30_minutes_is_failed_by_the_next_start(
    conn: psycopg.Connection, minutes_ago: int, cut_off: bool
) -> None:
    conn.execute(
        "INSERT INTO scan_runs (status, scope, started_at) VALUES ('running', 'full', %s)",
        (FIXED_TIME - timedelta(minutes=minutes_ago),),
    )
    if cut_off:
        start_run(conn, "full", FIXED_TIME)
        old = conn.execute("SELECT status FROM scan_runs WHERE id = 1").fetchone()
        assert old == ("failed",)
    else:
        with pytest.raises(psycopg.errors.UniqueViolation):
            start_run(conn, "full", FIXED_TIME)
