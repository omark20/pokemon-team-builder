import { expect, test } from "vitest";
import { matchupLevel, matchupWord } from "./matchupWords";

test.each([
  { points: -3, level: "bad", word: "Bad" },
  { points: -2, level: "bad", word: "Bad" },
  { points: -1, level: "weak", word: "Weak" },
  { points: 0, level: "even", word: "Even" },
  { points: 1, level: "good", word: "Good" },
  { points: 2, level: "strong", word: "Strong" },
  { points: 3, level: "strong", word: "Strong" },
])("a matchup of $points is $level and reads $word", ({ points, level, word }) => {
  expect([matchupLevel(points), matchupWord(points)]).toEqual([level, word]);
});
