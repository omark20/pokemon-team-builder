"""The counter team for one of the visitor's teams, built by domain/counter.py.

The route loads the stored type chart and every stored Pokémon, passes them through
`candidate_pool`, the one place that decides who may be picked, and returns the search's
result as it is, plus the team size.
"""

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app import auth, db, limits
from app.domain.counter import Pokemon, build_counter_team, candidate_pool
from app.domain.types import Chart
from app.logs import log_event
from app.routes.params import PathId

logger = logging.getLogger(__name__)
router = APIRouter()

CHART_CELLS = 18 * 18
# At most this many counter teams are worked on at once, so the searches can never hold
# more than two of the four database connections or crowd out other visitors' reads.
COUNTER_PLACES = 2
COUNTER_WAIT_SECONDS = 2.0  # then 503, rather than holding a worker thread longer
EMPTY_TEAM_MESSAGE = "This team has no Pokémon yet. Add some to build its counter team."
FLAGS_NOT_LOADED = "The legendary flags are not loaded yet"
POKEMON_QUERY = """
    SELECT id, name, types, ARRAY[hp, attack, defense, special_attack, special_defense, speed],
           is_default, removed_at IS NOT NULL, is_legendary, is_mythical
    FROM pokemon
"""


@router.get("/api/teams/{team_id}/counter", dependencies=[Depends(limits.limit_counter)])
def counter_team(
    team_id: PathId, request: Request, leave_out_legendary: bool = False
) -> dict[str, Any]:
    """The counter team, one counter per slot; a message instead for an empty team.

    With `leave_out_legendary`, no legendary or mythical Pokémon (PokéAPI's own species
    flags) may be picked. A place is taken before any database work and given back after
    the search; with both places taken for two seconds, the answer is 503.
    """
    places = request.app.state.counter_places
    if not places.acquire(timeout=COUNTER_WAIT_SECONDS):
        log_event(logger, logging.WARNING, "counter_busy", request_id=request.state.request_id)
        raise HTTPException(503, "Counter teams are busy", headers={"Retry-After": "1"})
    try:
        return _counter_for(team_id, request, leave_out_legendary)
    finally:
        places.release()


def _counter_for(team_id: int, request: Request, leave_out_legendary: bool) -> dict[str, Any]:
    with db.connection_for(request) as conn:
        user_id = auth.current_user(request, conn)
        owned = conn.execute(
            "SELECT 1 FROM teams WHERE id = %s AND user_id = %s", (team_id, user_id)
        ).fetchone()
        if user_id is None or owned is None:
            raise HTTPException(404, "Team not found")
        members = conn.execute(
            "SELECT pokemon_id FROM team_members WHERE team_id = %s ORDER BY position", (team_id,)
        ).fetchall()
        if not members:
            return {"size": 0, "picks": [], "message": EMPTY_TEAM_MESSAGE}
        chart = _stored_chart(conn)
        stored = {p.id: p for p in _stored_pokemon(conn)}
    # The search runs after the connection is returned, so it holds none while it works.
    pool = candidate_pool(stored.values(), leave_out_legendary)
    if leave_out_legendary and not pool:
        # Until a scan has read the flags every one is unread, and unread is left out.
        raise HTTPException(503, FLAGS_NOT_LOADED)
    opponents = [stored[pokemon_id] for (pokemon_id,) in members]
    result = build_counter_team(opponents, pool, chart)
    return {"size": len(opponents), **asdict(result), "legendary_left_out": leave_out_legendary}


def _stored_chart(conn: db.Conn) -> Chart:
    """The stored chart, or 503 if the first scan has not loaded all of it."""
    rows = conn.execute("SELECT attacker, defender, multiplier FROM type_effectiveness")
    chart = {(attacker, defender): value for attacker, defender, value in rows}
    if len(chart) != CHART_CELLS:
        raise HTTPException(503, "The type chart is not loaded yet")
    return chart


def _stored_pokemon(conn: db.Conn) -> list[Pokemon]:
    return [
        Pokemon(pid, name, tuple(types), tuple(stats), is_default, removed, legendary, mythical)
        for pid, name, types, stats, is_default, removed, legendary, mythical in conn.execute(
            POKEMON_QUERY
        )
    ]
