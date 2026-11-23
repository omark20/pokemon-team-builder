// A team as GET /api/teams answers it, every slot on its usual four moves.
import type { Members, Team } from "../types";

export const makeTeam = (id: number, name: string, pokemon_ids: number[] = []): Team => ({
  id,
  name,
  pokemon_ids,
  moves: pokemon_ids.map(() => null),
});

// A team's slots holding these Pokémon, every one on its usual four.
export const usualMembers = (pokemon_ids: number[]): Members => ({ pokemon_ids, moves: pokemon_ids.map(() => null) });
