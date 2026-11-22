"""A stand-in for PokéAPI answering from the captured responses in samples/.

It serves the captured type list and all 21 type responses, and a Pokémon list holding
the 14 Pokémon whose detail responses were captured, each at its real listed URL.
Tests change `answers` to make PokéAPI say something else: a payload, None for a 404,
or an exception to raise.
"""

import copy
import json
from pathlib import Path
from typing import Any

import psycopg

from app.pokeapi import BASE_URL
from app.scan import run_scan, start_run, utc_now

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
TYPE_LIST = "type?limit=100"
POKEMON_LIST = "pokemon?limit=100000"


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def pokemon_path(pokemon_id: int) -> str:
    """The detail path as the list gives it, under BASE_URL."""
    return f"pokemon/{pokemon_id}/"


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
