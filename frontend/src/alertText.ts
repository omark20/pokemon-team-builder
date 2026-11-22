// How one change alert reads on the page, worked out from the change itself,
// the visitor's teams and the Pokémon list. Kept apart from the panel so each
// wording rule can be tested without drawing anything.
import { displayName, type Alert, type ChangeValue, type Pokemon, type Team } from "./types";

interface AlertRow {
  subject: string; // the Pokémon's name, or "Type chart"
  what: string; // the field, or for a removal the whole sentence
  oldValue: string | null; // null when the row shows no old and new value
  newValue: string | null;
  detected: string;
  affects: string; // which teams, or for a chart change which of your Pokémon
}

const WRITTEN_MULTIPLIERS: Record<string, string> = { "0": "0×", "0.25": "¼×", "0.5": "½×", "1": "1×", "2": "2×", "4": "4×" };

// Column names as words a reader knows; any other field shows its own name.
const FIELD_NAMES: Record<string, string> = {
  is_default: "special version",
  is_legendary: "legendary",
  is_mythical: "mythical",
  special_attack: "special attack",
  special_defense: "special defense",
  sprite_url: "picture",
  hp: "HP",
};

function formatValue(field: string, value: ChangeValue): string {
  if (field === "multiplier") return WRITTEN_MULTIPLIERS[String(value)] ?? `${String(value)}×`;
  if (field === "sprite_url") return value === null ? "none" : "a picture";
  if (field === "is_default") return value ? "no" : "yes"; // "special version" reads as the opposite
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function detectedOn(isoTime: string): string {
  const date = new Date(isoTime).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return `detected ${date}`;
}

function nameOf(id: number, pokemonById: Map<number, Pokemon>): string {
  return displayName(pokemonById.get(id)?.name ?? `Pokémon ${id}`);
}

// A Pokémon change names the teams holding it; a chart change names which of
// the visitor's Pokémon it touches.
function affectedText(alert: Alert, teams: Team[], pokemonById: Map<number, Pokemon>): string {
  if (alert.pokemon_id === null) {
    return `affects your ${alert.your_pokemon.map((id) => nameOf(id, pokemonById)).join(", ")}`;
  }
  const names = teams.filter((team) => team.pokemon_ids.some((id) => alert.your_pokemon.includes(id)));
  return `teams: ${names.map((team) => team.name).join(", ")}`;
}

// What changed: the two types of a chart cell, a sentence for a removal or a
// return to the list, or the field's name.
function whatChanged(alert: Alert): string {
  if (alert.pokemon_id === null) return `${alert.attacker} against ${alert.defender}`;
  if (alert.field !== "status") return FIELD_NAMES[alert.field] ?? alert.field;
  return alert.new_value === "removed" ? "no longer listed by PokéAPI" : "listed by PokéAPI again";
}

export function describeAlert(alert: Alert, teams: Team[], pokemonById: Map<number, Pokemon>): AlertRow {
  const isChart = alert.pokemon_id === null;
  const isStatus = alert.field === "status";
  return {
    subject: isChart ? "Type chart" : nameOf(alert.pokemon_id!, pokemonById),
    what: whatChanged(alert),
    oldValue: isStatus ? null : formatValue(alert.field, alert.old_value),
    newValue: isStatus ? null : formatValue(alert.field, alert.new_value),
    detected: detectedOn(alert.detected_at),
    affects: affectedText(alert, teams, pokemonById),
  };
}

// Whether an alert still touches a Pokémon on one of these teams. Alerts are
// read when the page opens; one for a Pokémon since taken off every team is
// no longer shown.
export function touchesTeams(alert: Alert, teams: Team[]): boolean {
  return teams.some((team) => team.pokemon_ids.some((id) => alert.your_pokemon.includes(id)));
}
