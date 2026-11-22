// Shapes of the data the backend sends, and the small facts about them that
// several components share.

// The 18 standard Pokémon types, in the order the games list them. The backend
// stores only these (the three extra types PokéAPI lists are dropped when the
// type chart is loaded), so every type a Pokémon carries is one of them.
export const TYPE_NAMES = [
  "normal", "fire", "water", "grass", "electric", "ice", "fighting", "poison", "ground",
  "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy",
] as const;

export type TypeName = (typeof TYPE_NAMES)[number];

// One entry of GET /api/pokemon. `stats` is always six base stats in the order
// of STAT_LABELS. `is_default` is false for special versions such as Mega and
// regional forms. `removed` is true when PokéAPI no longer serves the entry.
export interface Pokemon {
  id: number;
  name: string;
  is_default: boolean;
  types: TypeName[];
  stats: number[];
  sprite_url: string | null;
  removed: boolean;
}

// Short label shown on the card, and the full name read out by screen readers
// and shown on hover. Same order as `Pokemon.stats`.
export const STAT_LABELS = [
  { short: "HP", full: "Hit points" },
  { short: "Atk", full: "Attack" },
  { short: "Def", full: "Defense" },
  { short: "SpA", full: "Special attack" },
  { short: "SpD", full: "Special defense" },
  { short: "Spe", full: "Speed" },
] as const;

// PokéAPI names are lower case with dashes ("charizard-mega-x"); the page shows
// them with a capital first letter ("Charizard-mega-x").
export function displayName(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}
