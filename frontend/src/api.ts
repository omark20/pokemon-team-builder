// Every call the page makes to the backend. The browser talks to this app's
// own API only; it never calls PokéAPI.
import type { Pokemon } from "./types";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`GET ${path} answered ${response.status}`);
  return (await response.json()) as T;
}

// The whole stored Pokémon list, loaded once when the page opens.
export function fetchPokemon(): Promise<Pokemon[]> {
  return getJson<Pokemon[]>("/api/pokemon");
}
