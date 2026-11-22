"""What one worker thread of the scan does: fetch a Pokémon and its species, and parse them.

A worker returns a small result and drops the raw bodies, so memory stays flat however
large a response is. Saving happens in the scan's main thread (app/scan.py).
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from app.domain.diff import ParseError, PokemonRecord, parse_pokemon, parse_species, species_url
from app.pokeapi import UpstreamError

Fetch = Callable[[str], Any]


@dataclass(frozen=True)
class Fetched:
    """A worker's result: a record, or the reason there is none. Neither means a 404.

    A record whose species could not be read still has a reason: its flags were not read.
    """

    pokemon_id: int
    record: PokemonRecord | None = None
    reason: str | None = None
    rule: str | None = None


def fetch_one(fetch: Fetch, item: tuple[int, str]) -> Fetched:
    """Runs in a worker: fetch by the listed URL, parse, keep the record, drop the body."""
    pokemon_id, url = item
    try:
        payload = fetch(url)
    except UpstreamError as exc:
        return Fetched(pokemon_id, reason=exc.reason)
    if payload is None:
        return Fetched(pokemon_id)
    try:
        record = parse_pokemon(payload)
    except ParseError as exc:
        return Fetched(pokemon_id, reason="parse_error", rule=exc.rule)
    if record.id != pokemon_id:
        return Fetched(pokemon_id, reason="parse_error", rule="id_mismatch")
    return _with_species_flags(fetch, payload, record)


def _with_species_flags(fetch: Fetch, payload: Any, record: PokemonRecord) -> Fetched:
    """The record with its species' flags, or without them and the reason they are missing."""
    try:
        species = fetch(species_url(payload))
        if species is None:
            return Fetched(record.id, record, reason="species_http_404")
        is_legendary, is_mythical = parse_species(species)
    except UpstreamError as exc:
        return Fetched(record.id, record, reason=f"species_{exc.reason}")
    except ParseError as exc:
        return Fetched(record.id, record, reason="species_parse_error", rule=exc.rule)
    return Fetched(record.id, replace(record, is_legendary=is_legendary, is_mythical=is_mythical))
