// A counter response for the team Charizard, Blastoise, Venusaur. Its picks and
// totals are the full-pool reference result worked out for this team
// (Archeops, Hydrapple, Celesteela; 9, 6, 1677); the remaining numbers are what
// the counter core returns for it, which its own tests check against brute force.
import type { CounterResult } from "../types";

const pick = (opponent: [number, string], counter: [number, string], numbers: number[], type: string, reason: string) => ({
  opponent: { id: opponent[0], name: opponent[1] },
  counter: { id: counter[0], name: counter[1] },
  attack: numbers[0]!,
  attack_type: type,
  attack_back: numbers[1]!,
  matchup: numbers[2]!,
  coverage: numbers[3]!,
  base_stats: numbers[4]!,
  reason,
});

export const COUNTER: CounterResult = {
  picks: [
    pick([6, "charizard"], [567, "archeops"], [4, 0.5, 3, 3, 567], "rock",
      "Archeops (rock, flying) hits Charizard for 4× with rock attacks; Charizard's best attack back does ½×. Across the whole opposing team its matchups add up to +3."),
    pick([9, "blastoise"], [1019, "hydrapple"], [2, 0.25, 3, 1, 540], "grass",
      "Hydrapple (grass, dragon) hits Blastoise for 2× with grass attacks; Blastoise's best attack back does ¼×. Across the whole opposing team its matchups add up to +1."),
    pick([3, "venusaur"], [797, "celesteela"], [2, 0.25, 3, 2, 570], "flying",
      "Celesteela (steel, flying) hits Venusaur for 2× with flying attacks; Venusaur's best attack back does ¼×. Across the whole opposing team its matchups add up to +2."),
  ],
  totals: { assigned_points: 9, coverage: 6, base_stats: 1677 },
  grid: [
    [3, -1, 1],
    [-1, 3, -1],
    [-1, 0, 3],
  ],
  weakness_counts: { fire: 1, flying: 1, grass: 0, poison: 1, water: 1 },
  relaxed: false,
  stopped_early: false,
  pool_size: 1025,
};
