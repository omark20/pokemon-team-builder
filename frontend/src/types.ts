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

// A move chosen for a team slot, with its name, since a later scan may stop
// listing it for that Pokémon.
export interface ChosenMove {
  id: number;
  name: string;
}

// The moves chosen for one slot, or null for the Pokémon's default four.
export type SlotMoves = ChosenMove[] | null;

// One of the visitor's teams, as the backend sends it. `pokemon_ids` is in
// slot order and may hold the same Pokémon more than once; `moves` runs beside
// it, one entry per slot.
export interface Team {
  id: number;
  name: string;
  pokemon_ids: number[];
  moves: SlotMoves[];
}

// What a team's slots hold: the two lists that are saved together.
export type Members = Pick<Team, "pokemon_ids" | "moves">;

// Move names are written as words: "stone-edge" is "Stone Edge".
export function moveName(name: string): string {
  return name
    .split("-")
    .map((word) => displayName(word))
    .join(" ");
}

// How a counter's one on one fight with an opponent ends, for the counter.
export type Outcome = "wins" | "draws with" | "loses to";

// GET /api/teams/{id}/counter, as far as the page reads it. A fight's damage,
// accuracy and HP are stated in its pick's `reason`.

// One side of a fight: the Pokémon, the move it uses (null when none of its four
// damages the other side) and the turns it needs to knock the other out, 1 to 10,
// where 10 means "10 or more".
export interface FightSide {
  id: number;
  name: string;
  move: string | null;
  turns: number;
}

// One counter and the opponent it was picked for. `line` says how their fight ends
// in one sentence; `reason` gives the numbers behind it.
export interface CounterPick {
  counter: FightSide;
  opponent: FightSide;
  outcome: Outcome;
  line: string;
  reason: string;
}

// One cell of the table of every fight.
export interface FightCell {
  outcome: Outcome;
  counter_turns: number;
  opponent_turns: number;
}

// The four moves one of the visitor's Pokémon is assumed to carry.
export interface AssumedMoves {
  name: string;
  moves: string[];
  moves_listed: boolean; // false when PokéAPI lists no moves for it at all
}

// Whether the team keeps the rule that no opposing type hits more than half the
// counters for 2× or more: kept; no team could keep it; or the search for a team
// that keeps it was cut short, so the best team regardless is shown.
export type WeaknessRule = "kept" | "limit_raised" | "guard_reached";

// The counter team, in the order of the team it answers. `grid[i][j]` is counter i
// against opponent j; against the opponent it was picked for, a counter's cell is
// the fight its pick describes.
export interface CounterResult {
  picks: CounterPick[];
  grid: FightCell[][];
  opponent_moves: AssumedMoves[];
  weakness_counts: Record<string, number>; // per opposing type, in name order: counters it hits for 2× or more
  weakness_rule: WeaknessRule;
  pool_size: number;
  // An opponent nothing left can hit for 2× or more, once Pokémon are left out;
  // when set there is no team.
  no_candidate_for: string | null;
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
  failed: number; // Pokémon that could not be read in this run
}
