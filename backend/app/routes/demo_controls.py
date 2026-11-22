"""The demo controls, behind ADMIN_TOKEN: store "what PokéAPI said" patches, and reset.

Each patch is validated like real data: standard type names, base stats from 0 to 255,
a sprite on PokéAPI's sprite host or none, at most 20 Pokémon. Storing a document
changes nothing else; the next scan applies it (app/demo.py).
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app import auth, db, demo, pokemon_list
from app.domain.diff import MAX_BASE_STAT, SPRITE_PREFIX
from app.domain.types import STANDARD_TYPES
from app.routes.params import MAX_ID

router = APIRouter(prefix="/api/admin/demo", dependencies=[Depends(auth.require_admin_token)])
STRICT = ConfigDict(extra="forbid", strict=True)


def _standard_type(name: str) -> str:
    if name not in STANDARD_TYPES:
        raise ValueError("not one of the 18 standard types")
    return name


def _sprite(url: str) -> str:
    if not url.startswith(SPRITE_PREFIX):
        raise ValueError("not on PokéAPI's sprite host")
    return url


def _multiplier(value: float) -> float:
    if value not in (0, 0.5, 1, 2):
        raise ValueError("a type-chart multiplier is 0, 0.5, 1 or 2")
    return value


TypeName = Annotated[str, AfterValidator(_standard_type)]
BaseStat = Annotated[int, Field(ge=0, le=MAX_BASE_STAT)]
PokemonKey = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,9}$")]


class PokemonPatch(BaseModel):
    """The fields PokéAPI is to be believed to say; only those sent are patched."""

    model_config = STRICT
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    types: Annotated[list[TypeName], Field(min_length=1, max_length=2)] | None = None
    hp: BaseStat | None = None
    attack: BaseStat | None = None
    defense: BaseStat | None = None
    special_attack: BaseStat | None = None
    special_defense: BaseStat | None = None
    speed: BaseStat | None = None
    sprite_url: Annotated[str, AfterValidator(_sprite)] | None = None
    removed: Literal[True] | None = None

    @model_validator(mode="after")
    def _only_sprite_may_be_none(self) -> "PokemonPatch":
        nulls = {name for name in self.model_fields_set if getattr(self, name) is None}
        if nulls - {"sprite_url"}:
            raise ValueError("only sprite_url may be null")
        if self.types is not None and len(set(self.types)) != len(self.types):
            raise ValueError("a type may appear once")
        return self


class CellPatch(BaseModel):
    model_config = STRICT
    attacker: TypeName
    defender: TypeName
    multiplier: Annotated[float, AfterValidator(_multiplier)]


class OverridesBody(BaseModel):
    model_config = STRICT
    pokemon: dict[PokemonKey, PokemonPatch] = Field(default_factory=dict, max_length=20)
    type_chart: list[CellPatch] = Field(default_factory=list, max_length=18 * 18)


@router.put("/overrides")
def put_overrides(request: Request, body: OverridesBody) -> dict[str, Any]:
    """Store the document, replacing any earlier one, and return it as stored."""
    with db.connection_for(request) as conn:
        wanted = {int(key) for key in body.pokemon}
        found = conn.execute("SELECT id FROM pokemon WHERE id = ANY(%s)", (list(wanted),))
        if max(wanted, default=0) > MAX_ID or {pid for (pid,) in found} != wanted:
            raise HTTPException(422, "Unknown Pokémon ID")
        doc = {
            "pokemon": {
                key: patch.model_dump(exclude_unset=True) for key, patch in body.pokemon.items()
            },
            "type_chart": [cell.model_dump() for cell in body.type_chart],
        }
        demo.store(conn, doc)
        return doc


@router.post("/reset")
def reset(request: Request) -> dict[str, int]:
    """Undo every demo change and drop the document; then clear the list held in memory."""
    with db.connection_for(request) as conn:
        result = demo.reset(conn)
    # Cleared only after the commit, so a rebuild cannot pick up the patched values.
    pokemon_list.clear("demo_reset")
    return result
