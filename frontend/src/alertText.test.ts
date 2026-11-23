// The wording of an alert row for each kind of change the backend reports: a stat, the types, the picture,
// the legendary flag, an unknown field, a removed Pokémon, and a type-chart cell.
import { expect, test } from "vitest";
import { describeAlert, touchesTeams } from "./alertText";
import { CENSUS } from "./test/census";
import type { Alert, Team } from "./types";
import { makeTeam } from "./test/makeTeam";

const BY_ID = new Map(CENSUS.map((entry) => [entry.id, entry]));
const TEAMS: Team[] = [
  makeTeam(1, "Alpha", [6, 3]),
  makeTeam(2, "Beta", [6]),
  makeTeam(3, "Gamma", [25]),
];

const alert = (change: Partial<Alert>): Alert => ({
  id: 1, pokemon_id: 6, attacker: null, defender: null, move: null, field: "attack", old_value: 84, new_value: 94,
  detected_at: "2026-11-20T12:00:00Z", is_demo: false, your_pokemon: [6], ...change,
});

test.each([
  {
    change: "a stat",
    alert: alert({}),
    row: { subject: "Charizard", what: "attack", oldValue: "84", newValue: "94", affects: "teams: Alpha, Beta" },
  },
  {
    change: "the types",
    alert: alert({ field: "types", old_value: ["fire", "flying"], new_value: ["fire", "dragon"] }),
    row: { what: "types", oldValue: "fire, flying", newValue: "fire, dragon" },
  },
  {
    change: "a picture removed",
    alert: alert({ field: "sprite_url", old_value: "https://raw.githubusercontent.com/x.png", new_value: null }),
    row: { what: "picture", oldValue: "a picture", newValue: "none" },
  },
  {
    change: "the legendary flag",
    alert: alert({ field: "is_legendary", old_value: false, new_value: true }),
    row: { what: "legendary", oldValue: "no", newValue: "yes" },
  },
  {
    change: "a field the page does not know",
    alert: alert({ field: "weight", old_value: 905, new_value: 910 }),
    row: { what: "weight", oldValue: "905", newValue: "910" },
  },
  {
    change: "a removal",
    alert: alert({ field: "status", old_value: "available", new_value: "removed" }),
    row: { what: "no longer listed by PokéAPI", oldValue: null, newValue: null },
  },
  {
    change: "a type-chart cell",
    alert: alert({ pokemon_id: null, attacker: "fire", defender: "grass", field: "multiplier", old_value: 2, new_value: 1, your_pokemon: [6, 3] }),
    row: { subject: "Type chart", what: "fire against grass", oldValue: "2×", newValue: "1×", affects: "affects your Charizard, Venusaur" },
  },
  {
    change: "a halved multiplier",
    alert: alert({ pokemon_id: null, attacker: "fire", defender: "water", field: "multiplier", old_value: 1, new_value: 0.5 }),
    row: { oldValue: "1×", newValue: "½×" },
  },
])("an alert for $change reads as expected", ({ alert: change, row }) => {
  expect(describeAlert(change, TEAMS, BY_ID)).toMatchObject(row);
});

// A move alert: no Pokémon or chart cell; `your_pokemon` are the team members carrying it.
const moveAlert = (field: string, oldValue: number | string | null, newValue: number | string | null, yours = [6]) =>
  alert({ pokemon_id: null, move: "flamethrower", field, old_value: oldValue, new_value: newValue, your_pokemon: yours });

test.each([
  { change: "its power", alert: moveAlert("power", 90, 95), row: { what: "power", oldValue: "90", newValue: "95" } },
  { change: "its accuracy", alert: moveAlert("accuracy", 100, 85), row: { what: "accuracy", oldValue: "100", newValue: "85" } },
  { change: "its accuracy to none", alert: moveAlert("accuracy", 90, null), row: { what: "accuracy", oldValue: "90", newValue: "none" } },
  { change: "its type", alert: moveAlert("type", "fire", "water"), row: { what: "type", oldValue: "fire", newValue: "water" } },
  { change: "its kind", alert: moveAlert("damage_class", "special", "physical"), row: { what: "kind", oldValue: "special", newValue: "physical" } },
])("a move alert for $change names the move and the field", ({ alert: change, row }) => {
  expect(describeAlert(change, TEAMS, BY_ID)).toMatchObject({ subject: "Flamethrower", affects: "used by your Charizard", ...row });
});

test("a move alert names every one of your Pokémon that carries it", () => {
  expect(describeAlert(moveAlert("power", 90, 95, [6, 25]), TEAMS, BY_ID).affects).toBe("used by your Charizard, Pikachu");
});

test("a move alert is kept while a Pokémon that carries it is on a team", () => {
  expect(touchesTeams(moveAlert("power", 90, 95, [25]), TEAMS)).toBe(true);
  expect(touchesTeams(moveAlert("power", 90, 95, [150]), TEAMS)).toBe(false);
});

test("the detection date is written as day and month", () => {
  expect(describeAlert(alert({}), TEAMS, BY_ID).detected).toBe("detected 20 Nov");
});

test("an alert is kept only while one of its Pokémon is on a team", () => {
  expect(touchesTeams(alert({ your_pokemon: [6] }), TEAMS)).toBe(true);
  expect(touchesTeams(alert({ your_pokemon: [9] }), TEAMS)).toBe(false);
});
