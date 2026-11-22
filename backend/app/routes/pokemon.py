"""The public list of every stored Pokémon, answered from memory (app/pokemon_list.py)."""

from functools import partial

from fastapi import APIRouter, Request, Response

from app import db, pokemon_list

router = APIRouter()


@router.get("/api/pokemon")
def list_pokemon(request: Request) -> Response:
    """Every stored Pokémon with its types, six base stats, sprite and removed flag.

    Opens a database connection only when the in-memory copy has to be built.
    """
    body = pokemon_list.get(partial(db.connection_for, request))
    return Response(body, media_type="application/json")
