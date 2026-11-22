// Test fixture: the full Pokémon list in the shape of GET /api/pokemon, built
// from samples/census_all_pokemon.tsv (one row per entry of PokéAPI's list,
// extracted from the captured detail responses). No entry is marked removed.
import censusText from "../../../samples/census_all_pokemon.tsv?raw";
import type { Pokemon, TypeName } from "../types";

function parseRow(row: string): Pokemon {
  const [id, name, , isDefault, types, ...rest] = row.split("\t");
  const sprite = rest[6];
  return {
    id: Number(id),
    name: name ?? "",
    is_default: isDefault === "true",
    types: (types ?? "").split("/") as TypeName[],
    stats: rest.slice(0, 6).map(Number),
    sprite_url: sprite === "null" ? null : (sprite ?? null),
    removed: false,
  };
}

export const CENSUS: Pokemon[] = censusText.trim().split("\n").slice(1).map(parseRow);

export function byName(name: string): Pokemon {
  const found = CENSUS.find((pokemon) => pokemon.name === name);
  if (!found) throw new Error(`no census entry named ${name}`);
  return found;
}
