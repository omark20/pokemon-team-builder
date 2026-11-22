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

// One of the visitor's teams, as the backend sends it. `pokemon_ids` is in
// slot order and may hold the same Pokémon more than once.
export interface Team {
  id: number;
  name: string;
  pokemon_ids: number[];
}

// One counter in GET /api/teams/{id}/counter: the opponent it answers and the
// numbers behind the choice. Multipliers are 0, 0.25, 0.5, 1, 2 or 4.
export interface CounterPick {
  opponent: { id: number; name: string };
  counter: { id: number; name: string };
  attack: number; // the counter's best multiplier on its opponent
  attack_type: string; // the counter's type that gives it
  attack_back: number; // the opponent's best multiplier on the counter
  matchup: number; // points: how hard it hits minus how hard it is hit, -5 to 5
  coverage: number; // its matchups against every opponent, added up
  base_stats: number;
  reason: string;
}

// The counter team, in the order of the team it answers. `grid[i][j]` is the
// matchup of counter i against opponent j. `weakness_counts` gives, for each
// opposing type, how many counters it hits for 2x or more.
export interface CounterResult {
  picks: CounterPick[];
  totals: { assigned_points: number; coverage: number; base_stats: number };
  grid: number[][];
  weakness_counts: Record<string, number>;
  relaxed: boolean; // more than half the counters share a weakness: no team avoided it
  stopped_early: boolean; // the search hit its step limit; a better team may exist
  pool_size: number;
  legendary_left_out: boolean; // the candidates excluded legendary and mythical Pokémon
}

// A value as the scan recorded it: a number (a stat or a multiplier), text,
// a list of type names, true or false, or null (no picture).
export type ChangeValue = number | string | string[] | boolean | null;

// One entry of GET /api/alerts: a change from the last seven days that touches
// the visitor's Pokémon. A Pokémon change has `pokemon_id`; a type-chart change
// has `attacker` and `defender` instead. `your_pokemon` lists, once each, the
// visitor's Pokémon the change touches.
export interface Alert {
  id: number;
  pokemon_id: number | null;
  attacker: string | null;
  defender: string | null;
  field: string;
  old_value: ChangeValue;
  new_value: ChangeValue;
  detected_at: string;
  is_demo: boolean;
  your_pokemon: number[];
}

// One run of the scan for changes, newest first in GET /api/scan/status.
export interface ScanRun {
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "incomplete" | "failed";
  scanned: number;
  changed: number;
}
