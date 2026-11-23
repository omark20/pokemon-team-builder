"""A stand-in for PokéAPI answering from the captured responses in samples/.

It serves the captured type list and all 21 type responses, a move list holding the 14
moves whose answers were captured and those 14 answers, a Pokémon list holding the 14
Pokémon whose detail responses were captured, each at its real listed URL, and the
captured species responses those 14 name.
Tests change `answers` to make PokéAPI say something else: a payload, None for a 404,
or an exception to raise.
"""

import copy
import csv
import json
from pathlib import Path
from typing import Any

import psycopg

from app.domain.moves import Move
from app.pokeapi import BASE_URL
from app.scan import run_scan, start_run, utc_now

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
TYPE_LIST = "type?limit=100"
POKEMON_LIST = "pokemon?limit=100000"
MOVE_LIST = "move?limit=100000"


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def pokemon_path(pokemon_id: int) -> str:
    """The detail path as the list gives it, under BASE_URL."""
    return f"pokemon/{pokemon_id}/"


def census_moves() -> dict[int, Move]:
    """Every move in census_all_moves.tsv by ID, as a Move; an empty cell is a null upstream.

    The census has no effect text, so `short_effect` is None in every one.
    """
    with (SAMPLES / "census_all_moves.tsv").open() as file:
        rows = list(csv.DictReader(file, delimiter="\t"))
    return {
        int(row["id"]): Move(
            int(row["id"]),
            row["name"],
            row["type"],
            row["damage_class"],
            int(row["power"]) if row["power"] else None,
            int(row["accuracy"]) if row["accuracy"] else None,
            int(row["priority"]),
            None,
        )
        for row in rows
    }


def move_path(move_id: int) -> str:
    """The move path as the move list gives it, under BASE_URL."""
    return f"move/{move_id}/"


def species_path(species_id: int) -> str:
    """The species path as a detail response names it, under BASE_URL."""
    return f"pokemon-species/{species_id}/"


class FakePokeApi:
    """Answers `get(path)` like PokeApiSource, from a dictionary keyed by path."""

    def __init__(self) -> None:
        self.answers: dict[str, Any] = {TYPE_LIST: _load(SAMPLES / "type_list.json")}
        for path in SAMPLES.glob("type_*_*.json"):
            type_id = path.name.split("_")[1]
            self.answers[f"type/{type_id}/"] = _load(path)
        details = {_load(p)["id"]: _load(p) for p in SAMPLES.glob("pokemon_[0-9]*_*.json")}
        full_list = _load(SAMPLES / "pokemon_list_full.json")["results"]
        results = [e for e in full_list if int(e["url"].rstrip("/").rsplit("/", 1)[1]) in details]
        self.answers[POKEMON_LIST] = {"count": len(results), "results": results}
        for pokemon_id, payload in details.items():
            self.answers[pokemon_path(pokemon_id)] = payload
        for path in SAMPLES.glob("species_[0-9]*_*.json"):
            species = _load(path)
            self.answers[species_path(species["id"])] = species
        moves = {_load(p)["id"]: _load(p) for p in SAMPLES.glob("move_[0-9]*_*.json")}
        all_moves = _load(SAMPLES / "move_list_full.json")["results"]
        listed = [e for e in all_moves if int(e["url"].rstrip("/").rsplit("/", 1)[1]) in moves]
        self.answers[MOVE_LIST] = {"count": len(listed), "results": listed}
        for move_id, payload in moves.items():
            self.answers[move_path(move_id)] = payload
        self.requested: list[str] = []

    def get(self, path: str) -> Any:
        key = path.removeprefix(BASE_URL)
        self.requested.append(key)
        answer = self.answers[key]
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)

    def add_pokemon(self, pokemon_id: int) -> None:
        """List one more Pokémon, a copy of Charizard under a new ID and name."""
        payload = copy.deepcopy(self.answers[pokemon_path(6)]) | {
            "id": pokemon_id,
            "name": f"copy-{pokemon_id}",
        }
        self.answers[pokemon_path(pokemon_id)] = payload
        listing = self.answers[POKEMON_LIST]
        listing["results"].append(
            {"name": payload["name"], "url": BASE_URL + pokemon_path(pokemon_id)}
        )
        listing["count"] += 1


def run_fake_scan(conn: psycopg.Connection, source: FakePokeApi, **options: Any) -> tuple[int, str]:
    """Start and run one scan against the fake, with no waits between retries."""
    scope = "full" if options.get("pokemon_ids") is None else "subset"
    run_id = start_run(conn, scope, utc_now())
    return run_id, run_scan(conn, source, run_id, retry_waits=(0, 0, 0), **options)
