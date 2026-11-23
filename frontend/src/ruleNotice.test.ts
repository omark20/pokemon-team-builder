// The type-mix notice's sentence for each way the rule can be broken. The results
// are the counter fixture (Gyarados, Pikachu, Dragonite against Charizard, Blastoise,
// Venusaur) with the rule's state and the weakness counts set per case.
import { expect, test } from "vitest";
import { ruleNotice } from "./ruleNotice";
import { COUNTER } from "./test/counterFixture";
import type { CounterResult, WeaknessRule } from "./types";

const result = (rule: WeaknessRule, counts: Record<string, number>, size = 3): CounterResult => ({
  ...COUNTER,
  picks: COUNTER.picks.slice(0, size),
  weakness_counts: counts,
  weakness_rule: rule,
});

const NONE_FEWER = "No possible counter team has fewer than 2 weak to one of your team's types.";
const STOPPED =
  "This is the strongest team before the mix of types is considered; the search for a better-mixed one was stopped at its limit.";

test.each([
  ["one type, no team keeps the rule", result("limit_raised", { fire: 2, water: 1 }), `2 of these 3 counters are weak to Fire. ${NONE_FEWER}`],
  ["one type, the search stopped", result("guard_reached", { fire: 2, water: 1 }), `2 of these 3 counters are weak to Fire. ${STOPPED}`],
  ["two types share the largest count", result("limit_raised", { fire: 2, rock: 2, water: 1 }), `2 of these 3 counters are weak to Fire, and 2 to Rock. ${NONE_FEWER}`],
  ["three types share it", result("guard_reached", { fire: 2, rock: 2, water: 2 }), `2 of these 3 counters are weak to Fire, 2 to Rock, and 2 to Water. ${STOPPED}`],
  ["a team of one, one type", result("limit_raised", { fire: 1, flying: 0 }, 1), "Gyarados is weak to Fire. Every Pokémon that could be picked to counter Charizard is weak to one of its types."],
  ["a team of one, two types", result("limit_raised", { fire: 1, flying: 1 }, 1), "Gyarados is weak to Fire and Flying. Every Pokémon that could be picked to counter Charizard is weak to one of its types."],
])("%s", (_case, counter, sentence) => {
  expect(ruleNotice(counter)).toBe(sentence);
});

test("a team that keeps the rule has no notice", () => {
  expect(ruleNotice(result("kept", { fire: 1 }))).toBeNull();
});
