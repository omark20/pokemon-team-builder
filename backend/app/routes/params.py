"""Bounded integers for IDs in paths and bodies.

Every ID fits Postgres's integer and bigint columns, so an out-of-range value is a 422
from validation, never a database error.
"""

from typing import Annotated

from fastapi import Path
from pydantic import Field

MAX_ID = 2_147_483_647  # the largest Postgres integer

PokemonId = Annotated[int, Field(ge=1, le=MAX_ID)]
PathId = Annotated[int, Path(ge=1, le=MAX_ID)]
