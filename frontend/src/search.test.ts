// Expected results are read off samples/census_all_pokemon.tsv, not produced
// by the code under test.
import { expect, test } from "vitest";
import { filterPokemon, NO_FILTERS, searchPokemon, type GridFilters } from "./search";
import { CENSUS } from "./test/census";

const ids = (list: { id: number }[]) => list.map((pokemon) => pokemon.id);

// Starting with "char": 4, 5, 6, 737, 935, 10034, 10035, 10196. Containing it:
// chimchar (390) and pecharunt (1025).
const CHAR = [4, 5, 6, 737, 935, 10034, 10035, 10196, 390, 1025];
// charizard-mega-x, mewtwo-mega-x, raichu-mega-x.
const MEGA_X = [10034, 10043, 10304];

test.each([
  { rule: "starts-with before contains, each in ID order", query: "char", expected: CHAR },
  { rule: "capitals do not matter", query: "CHAR", expected: CHAR },
  { rule: "surrounding spaces are trimmed", query: "  char ", expected: CHAR },
  { rule: "a space matches a dash", query: "mega x", expected: MEGA_X },
  { rule: "a dash matches a dash", query: "mega-x", expected: MEGA_X },
  { rule: "a number matches the exact ID only", query: "25", expected: [25] },
  // Ivysaur is ID 2 and porygon2 has "2" in its name; IDs such as 12 or 20 do not match.
  { rule: "the exact ID comes before names containing the number", query: "2", expected: [2, 233] },
])("searchPokemon: $rule ($query)", ({ query, expected }) => {
  expect(ids(searchPokemon(CENSUS, query))).toEqual(expected);
});

test.each(["", "   "])("searchPokemon: the query '%s' returns the whole list in ID order", (query) => {
  expect(ids(searchPokemon([...CENSUS].reverse(), query))).toEqual(ids(CENSUS));
});

// 1,351 entries in all, 1,025 of them default; 96 carry ghost, 65 of those
// default; charizard-mega-x is the only "char" entry with the dragon type.
test.each<{ filters: Partial<GridFilters>; count: number }>([
  { filters: {}, count: 1351 },
  { filters: { hideSpecial: true }, count: 1025 },
  { filters: { type: "ghost" }, count: 96 },
  { filters: { type: "ghost", hideSpecial: true }, count: 65 },
  { filters: { query: "char", type: "dragon" }, count: 1 },
  { filters: { query: "char", type: "dragon", hideSpecial: true }, count: 0 },
])("filterPokemon: $filters leaves $count", ({ filters, count }) => {
  expect(filterPokemon(CENSUS, { ...NO_FILTERS, ...filters })).toHaveLength(count);
});

test("filterPokemon leaves out entries marked removed", () => {
  const list = CENSUS.map((pokemon) => (pokemon.id === 6 ? { ...pokemon, removed: true } : pokemon));
  expect(ids(filterPokemon(list, NO_FILTERS))).not.toContain(6);
});
