"""The counter team for one of the visitor's teams, built by domain/counter.py.

The route loads the stored type chart and every stored Pokémon with the four moves it
carries and its baseline (duel_store.py), all in one borrowed connection. Candidates are
the field, the Pokémon with a stored baseline, passed through `candidate_pool`, the one
place that decides who may be picked; the field's size is the N the baselines were
taken over. The core's result is returned as it is, plus the team size.
"""

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app import auth, db, duel_store, limits
from app.domain.counter import build_counter_team, candidate_pool
from app.logs import log_event
from app.routes.params import PathId

logger = logging.getLogger(__name__)
router = APIRouter()

# At most this many counter teams are worked on at once, so the searches can never hold
# more than two of the four database connections or crowd out other visitors' reads.
COUNTER_PLACES = 2
COUNTER_WAIT_SECONDS = 2.0  # then 503, rather than holding a worker thread longer
EMPTY_TEAM_MESSAGE = "This team has no Pokémon yet. Add some to build its counter team."
FLAGS_NOT_LOADED = "The legendary flags are not loaded yet"
CHART_NOT_LOADED = "The type chart is not loaded yet"
MOVES_NOT_LOADED = "The moves are not loaded yet"


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
        if request.app.state.limiter.first_refusal("counter", limits.client_address(request)):
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
        chart = duel_store.load_chart(conn)
        if chart is None:
            raise HTTPException(503, CHART_NOT_LOADED)
        fighters = duel_store.load_fighters(conn)
        if fighters is None:
            raise HTTPException(503, MOVES_NOT_LOADED)
    # The search runs after the connection is returned, so it holds none while it works.
    pool = candidate_pool(fighters.field, leave_out_legendary)
    if leave_out_legendary and not pool:
        # Until a scan has read the flags every one is unread, and unread is left out.
        raise HTTPException(503, FLAGS_NOT_LOADED)
    opponents = [fighters.by_id[pokemon_id] for (pokemon_id,) in members]
    result = build_counter_team(opponents, pool, chart, len(fighters.field))
    return {"size": len(opponents), **asdict(result), "legendary_left_out": leave_out_legendary}
