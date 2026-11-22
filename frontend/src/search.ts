// Searching and filtering the Pokémon list in the browser. Nothing here talks
// to the server: the whole list is already loaded.
import type { Pokemon, TypeName } from "./types";

export interface GridFilters {
  query: string;
  type: TypeName | "";
  hideSpecial: boolean;
}

export const NO_FILTERS: GridFilters = { query: "", type: "", hideSpecial: false };

// Lower case with dashes as spaces, so "Mega X" and "mega-x" compare equal.
function normalise(text: string): string {
  return text.toLowerCase().replace(/-/g, " ");
}

// How well one Pokémon matches a normalised query: 0 for its exact number,
// 1 when its name starts with the query, 2 when the name contains it, and
// null for no match.
function matchRank(pokemon: Pokemon, query: string): number | null {
  if (String(pokemon.id) === query) return 0;
  const name = normalise(pokemon.name);
  if (name.startsWith(query)) return 1;
  if (name.includes(query)) return 2;
  return null;
}

// The Pokémon matching `query`, best matches first: exact number, then names
// starting with the query, then names containing it, each group in ID order.
// An empty query returns the whole list in ID order.
export function searchPokemon(list: Pokemon[], query: string): Pokemon[] {
  const wanted = normalise(query.trim());
  const ranked: { rank: number; pokemon: Pokemon }[] = [];
  for (const pokemon of list) {
    const rank = wanted === "" ? 0 : matchRank(pokemon, wanted);
    if (rank !== null) ranked.push({ rank, pokemon });
  }
  ranked.sort((a, b) => a.rank - b.rank || a.pokemon.id - b.pokemon.id);
  return ranked.map((entry) => entry.pokemon);
}

// The grid's contents: entries PokéAPI still serves that pass the type filter
// and the "hide special versions" checkbox, ordered by the search.
export function filterPokemon(list: Pokemon[], filters: GridFilters): Pokemon[] {
  const kept = list.filter(
    (pokemon) =>
      !pokemon.removed &&
      (filters.type === "" || pokemon.types.includes(filters.type)) &&
      (!filters.hideSpecial || pokemon.is_default),
  );
  return searchPokemon(kept, filters.query);
}
