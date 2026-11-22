"""The counter score's table of levels against what its functions really return.

The table's weights are checked elsewhere against the bounds typed into it; this checks
those bounds against the data. A matchup depends only on the two Pokémon's types, so
every pair of type combinations in the census stands for every pair of Pokémon.
"""

import csv
import itertools
import json
from pathlib import Path

from app.domain.counter import SCORE_LEVELS, Pokemon, matchup
from app.domain.types import build_chart

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def test_matchup_stays_within_the_tables_bounds_for_every_pair_in_the_census() -> None:
    chart = build_chart(json.loads(p.read_text()) for p in SAMPLES.glob("type_*_*.json"))
    rows = csv.DictReader((SAMPLES / "census_all_pokemon.tsv").open(), delimiter="\t")
    type_sets = {tuple(row["types"].split("/")) for row in rows}
    stand_ins = [Pokemon(0, "/".join(types), types, (0,) * 6) for types in sorted(type_sets)]
    level = next(row for row in SCORE_LEVELS if row.name == "assigned_points")
    pairs = itertools.product(stand_ins, repeat=2)
    values = {matchup(counter, opponent, chart) for counter, opponent in pairs}
    assert level.smallest <= min(values) and max(values) <= level.largest
