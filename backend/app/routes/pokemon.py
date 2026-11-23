"""The public list of every stored Pokémon, answered from memory (app/pokemon_list.py),
and the moves one Pokémon may be given in a duel."""

from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app import db, duel_store, pokemon_list
from app.chosen_moves import counted
from app.routes.counter import MOVES_NOT_LOADED
from app.routes.params import PathId

router = APIRouter()
MOVE_FIELDS = ("id", "name", "type", "damage_class", "power", "accuracy")


@router.get("/api/pokemon")
def list_pokemon(request: Request) -> Response:
    """Every stored Pokémon with its types, six base stats, sprite and removed flag.

    Opens a database connection only when the in-memory copy has to be built.
    """
    body = pokemon_list.get(partial(db.connection_for, request))
    return Response(body, media_type="application/json")


@router.get("/api/pokemon/{pokemon_id}/moves")
def pokemon_moves(pokemon_id: PathId, request: Request) -> dict[str, Any]:
    """The moves this Pokémon can learn that count in a duel, by ID, and its default four.

    `accuracy` is null or 0 for a move that cannot miss. `moves_listed` is false where
    PokéAPI lists no moves for it at all.
    """
    with db.connection_for(request) as conn:
        row = conn.execute(
            "SELECT m.move_ids, d.move_ids FROM pokemon p"
            " LEFT JOIN pokemon_moves m ON m.pokemon_id = p.id"
            " LEFT JOIN duel_data d ON d.pokemon_id = p.id WHERE p.id = %s",
            (pokemon_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Pokémon not found")
        listed, default = row
        if listed is None:  # its answer has not been read by a scan with moves
            raise HTTPException(503, MOVES_NOT_LOADED)
        moves = duel_store.load_moves_named(conn, listed)
    usable = sorted(i for i in moves if counted(i, moves))
    return {
        "moves": [{field: getattr(moves[i], field) for field in MOVE_FIELDS} for i in usable],
        "default": default or [],
        "moves_listed": listed != [],
    }
